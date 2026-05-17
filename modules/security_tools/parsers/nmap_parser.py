"""Deterministic nmap XML → structured Observation parser.

Uses the stdlib `xml.etree.ElementTree` (no external dep). The planner / LLM
only ever sees the structured output produced here, never raw nmap stdout.

Return shape:
{
  "status": "success" | "partial" | "failure",
  "summary": str,
  "structured_data": {
    "hosts": [
      {
        "address": "192.168.1.10",
        "address_type": "ipv4",
        "state": "up" | "down" | "unknown",
        "hostname": "" | "...",
        "open_ports": [22, 80, ...],
        "services": [
          {"port": 22, "protocol": "tcp", "service_name": "ssh",
           "version_hint": "OpenSSH 9.x" | ""}
        ]
      }
    ],
    "scan_args": "...",
    "scan_started": "..."
  },
  "errors": [str, ...]
}
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


def parse_nmap_xml(xml_bytes: bytes | str) -> dict[str, Any]:
    """Parse nmap -oX - output. Tolerant of partial / truncated XML."""
    if not xml_bytes:
        return _empty("no nmap output")

    if isinstance(xml_bytes, bytes):
        try:
            xml_text = xml_bytes.decode("utf-8", errors="replace")
        except Exception:
            return _empty("nmap output was not decodable as UTF-8")
    else:
        xml_text = xml_bytes

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return {
            "status": "failure",
            "summary": "nmap XML parse failed",
            "structured_data": {"hosts": [], "scan_args": "", "scan_started": ""},
            "errors": [f"XML parse error: {exc}"],
        }

    hosts: list[dict[str, Any]] = []
    for host_el in root.findall("host"):
        hosts.append(_parse_host(host_el))

    scan_args = root.attrib.get("args", "")
    scan_started = root.attrib.get("startstr", "") or root.attrib.get("start", "")
    total_ports = sum(len(h["open_ports"]) for h in hosts)
    live_hosts = [h for h in hosts if h["state"] == "up"]

    summary = (
        f"{len(live_hosts)} live host(s), {total_ports} open port(s) across "
        f"{len(hosts)} scanned target(s)"
    )

    # nmap exits successfully even when 0 hosts respond — that's still a valid
    # observation. We mark "partial" only when XML parsing recovered some
    # hosts but the document looked truncated.
    truncated = not xml_text.rstrip().endswith("</nmaprun>")
    status = "partial" if truncated and hosts else "success" if hosts or root.find("runstats") is not None else "failure"

    return {
        "status": status,
        "summary": summary,
        "structured_data": {
            "hosts": hosts,
            "scan_args": scan_args,
            "scan_started": scan_started,
        },
        "errors": [] if status != "failure" else ["nmap produced no host entries"],
    }


def _parse_host(host_el: ET.Element) -> dict[str, Any]:
    addr_el = host_el.find("address")
    address = addr_el.attrib.get("addr", "") if addr_el is not None else ""
    address_type = addr_el.attrib.get("addrtype", "ipv4") if addr_el is not None else "ipv4"

    status_el = host_el.find("status")
    state = status_el.attrib.get("state", "unknown") if status_el is not None else "unknown"

    hostname = ""
    hostnames_el = host_el.find("hostnames")
    if hostnames_el is not None:
        first = hostnames_el.find("hostname")
        if first is not None:
            hostname = first.attrib.get("name", "")

    open_ports: list[int] = []
    services: list[dict[str, Any]] = []

    ports_el = host_el.find("ports")
    if ports_el is not None:
        for port_el in ports_el.findall("port"):
            port_state_el = port_el.find("state")
            if port_state_el is None:
                continue
            if port_state_el.attrib.get("state") != "open":
                continue
            try:
                port_num = int(port_el.attrib.get("portid", "0"))
            except ValueError:
                continue
            protocol = port_el.attrib.get("protocol", "tcp")

            service_name = ""
            version_hint = ""
            svc_el = port_el.find("service")
            if svc_el is not None:
                service_name = svc_el.attrib.get("name", "")
                product = svc_el.attrib.get("product", "")
                version = svc_el.attrib.get("version", "")
                extrainfo = svc_el.attrib.get("extrainfo", "")
                version_hint = " ".join(p for p in (product, version, extrainfo) if p).strip()

            open_ports.append(port_num)
            services.append({
                "port": port_num,
                "protocol": protocol,
                "service_name": service_name,
                "version_hint": version_hint,
            })

    return {
        "address": address,
        "address_type": address_type,
        "state": state,
        "hostname": hostname,
        "open_ports": sorted(open_ports),
        "services": services,
    }


def _empty(reason: str) -> dict[str, Any]:
    return {
        "status": "failure",
        "summary": "no usable nmap output",
        "structured_data": {"hosts": [], "scan_args": "", "scan_started": ""},
        "errors": [reason],
    }
