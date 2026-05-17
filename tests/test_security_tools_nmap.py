"""Phase 1 tests — security tools capability extensions, nmap wrapper, parser.

Covers:
- CapabilityDescriptor security fields default safely and accept overrides.
- PermissionService scope/authorized-target checks.
- safety.validate_target / block_dangerous_flags / validate_ports.
- NmapWrapper refuses out-of-scope and dangerous-flag attempts (no subprocess).
- parse_nmap_xml handles a normal scan and an empty ping sweep.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.capability_registry import CapabilityDescriptor, CapabilityRegistry
from core.kernel.permissions import PermissionService
from modules.security_tools.parsers.nmap_parser import parse_nmap_xml
from modules.security_tools.safety import (
    block_dangerous_flags,
    validate_ports,
    validate_target,
)
from modules.security_tools.wrappers.nmap_wrapper import NmapWrapper


FIXTURES = Path(__file__).parent.parent / "modules" / "security_tools" / "fixtures"


# ---------------------------------------------------------------------------
# Descriptor extensions
# ---------------------------------------------------------------------------

def test_capability_descriptor_defaults_are_safe():
    d = CapabilityDescriptor(name="x", description="y")
    assert d.network_scope == "local"
    assert d.requires_authorization is False
    assert d.allowed_use_cases == []
    assert d.command_templates == {}
    assert d.parser == ""


def test_registry_persists_security_metadata():
    reg = CapabilityRegistry()
    reg.register_tool(
        {"name": "foo", "description": "demo", "parameters": {}},
        handler=lambda text, args: "ok",
        metadata={
            "network_scope": "lab",
            "requires_authorization": True,
            "command_templates": {"quick": "nmap -sT <target>"},
            "parser": "nmap_xml_v1",
            "allowed_use_cases": ["lab scan"],
        },
    )
    desc = reg.get_descriptor("foo")
    assert desc is not None
    assert desc.network_scope == "lab"
    assert desc.requires_authorization is True
    assert desc.command_templates == {"quick": "nmap -sT <target>"}
    assert desc.parser == "nmap_xml_v1"
    assert "lab scan" in desc.allowed_use_cases


def test_registry_existing_capabilities_still_work_without_security_fields():
    reg = CapabilityRegistry()
    reg.register_tool(
        {"name": "weather", "description": "demo", "parameters": {}},
        handler=lambda text, args: "ok",
        metadata={"connectivity": "online", "side_effect_level": "read"},
    )
    desc = reg.get_descriptor("weather")
    # Backward compat: defaults are present and don't break existing flows.
    assert desc.network_scope == "local"
    assert desc.requires_authorization is False


# ---------------------------------------------------------------------------
# PermissionService scope checks
# ---------------------------------------------------------------------------

def test_classify_target_scope():
    perms = PermissionService()
    assert perms.classify_target_scope("127.0.0.1") == "local"
    assert perms.classify_target_scope("localhost") == "local"
    assert perms.classify_target_scope("192.168.1.1") == "lab"
    assert perms.classify_target_scope("10.0.0.0/8") == "lab"
    assert perms.classify_target_scope("8.8.8.8") == "public"
    assert perms.classify_target_scope("example.com") == "unknown"


def test_check_network_scope_blocks_public_under_lab_scope():
    perms = PermissionService()
    ok, _ = perms.check_network_scope("192.168.1.10", "lab")
    assert ok is True
    ok, reason = perms.check_network_scope("8.8.8.8", "lab")
    assert ok is False
    assert "lab" in reason
    ok, reason = perms.check_network_scope("example.com", "lab")
    assert ok is False
    assert "unknown" in reason or "classified" in reason


def test_check_authorized_target_cidr_and_hostname():
    perms = PermissionService()
    ok, _ = perms.check_authorized_target("192.168.56.10", ["192.168.56.0/24", "10.0.0.0/8"])
    assert ok is True
    ok, _ = perms.check_authorized_target("172.20.0.5", ["192.168.56.0/24"])
    assert ok is False
    # Hostname suffix match
    ok, _ = perms.check_authorized_target("api.lab.local", ["lab.local"])
    assert ok is True
    ok, _ = perms.check_authorized_target("api.lab.local", ["other.local"])
    assert ok is False


# ---------------------------------------------------------------------------
# safety helpers
# ---------------------------------------------------------------------------

def test_validate_target_accepts_loopback_under_local_scope():
    check = validate_target("127.0.0.1", allowed_scope="local")
    assert check.allowed is True
    assert check.scope == "local"


def test_validate_target_refuses_public_under_lab_scope():
    check = validate_target("8.8.8.8", allowed_scope="lab", authorized_scopes=[])
    assert check.allowed is False


def test_validate_target_requires_authorized_scope_when_lab():
    # Even though 192.168.x is RFC1918, it must also match config allowlist.
    check = validate_target(
        "192.168.99.5",
        allowed_scope="lab",
        authorized_scopes=["192.168.56.0/24"],
    )
    assert check.allowed is False
    check = validate_target(
        "192.168.56.5",
        allowed_scope="lab",
        authorized_scopes=["192.168.56.0/24"],
    )
    assert check.allowed is True


def test_block_dangerous_flags_catches_script_and_metachars():
    assert block_dangerous_flags("nmap --script vuln 1.1.1.1")
    assert block_dangerous_flags("nmap -O 1.1.1.1")
    assert block_dangerous_flags("nmap 1.1.1.1; rm -rf /")
    assert block_dangerous_flags("nmap -f 1.1.1.1")
    assert block_dangerous_flags("nmap -sT -oX - 127.0.0.1") is None


def test_validate_ports():
    assert validate_ports("22,80,443")[0] is True
    assert validate_ports("1-1024")[0] is True
    assert validate_ports("80,443,8000-8100")[0] is True
    assert validate_ports("80; rm")[0] is False
    assert validate_ports("70000")[0] is False
    assert validate_ports("")[0] is True
    assert validate_ports(None)[0] is True


# ---------------------------------------------------------------------------
# NmapWrapper safety refusals (no subprocess)
# ---------------------------------------------------------------------------

def test_nmap_wrapper_refuses_public_target_without_subprocess():
    wrap = NmapWrapper(authorized_scopes=["192.168.56.0/24"])
    result = wrap.host_service_scan("8.8.8.8", profile="quick", allowed_scope="lab")
    assert result.status == "refused"
    assert result.command == ""  # never reached subprocess


def test_nmap_wrapper_refuses_unauthorized_subnet():
    wrap = NmapWrapper(authorized_scopes=["192.168.56.0/24"])
    result = wrap.ping_sweep("10.0.0.0/24", allowed_scope="lab")
    assert result.status == "refused"


def test_nmap_wrapper_accepts_authorized_loopback_for_local_scope():
    wrap = NmapWrapper(authorized_scopes=[])
    # We don't run subprocess in unit tests — just verify safety passes by
    # using a non-existent binary path so subprocess fails fast.
    wrap.binary = "/nonexistent/nmap-binary"
    result = wrap.host_service_scan("127.0.0.1", profile="quick", allowed_scope="local")
    assert result.status == "failure"   # binary not found, but scope check passed
    assert "binary not found" in result.reason


def test_nmap_wrapper_rejects_invalid_port_spec():
    wrap = NmapWrapper(authorized_scopes=[])
    wrap.binary = "/nonexistent/nmap-binary"
    result = wrap.host_service_scan(
        "127.0.0.1", profile="quick", ports="80; rm", allowed_scope="local",
    )
    assert result.status == "refused"
    assert "port" in result.reason.lower()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_parse_nmap_xml_normal_scan():
    xml = (FIXTURES / "nmap_localhost_open.xml").read_bytes()
    obs = parse_nmap_xml(xml)
    assert obs["status"] == "success"
    hosts = obs["structured_data"]["hosts"]
    assert len(hosts) == 1
    h = hosts[0]
    assert h["address"] == "127.0.0.1"
    assert h["state"] == "up"
    assert 22 in h["open_ports"]
    assert 80 in h["open_ports"]
    assert 443 in h["open_ports"]
    ssh = next(s for s in h["services"] if s["port"] == 22)
    assert ssh["service_name"] == "ssh"
    assert "OpenSSH" in ssh["version_hint"]


def test_parse_nmap_xml_empty_sweep_is_success_not_failure():
    xml = (FIXTURES / "nmap_no_hosts.xml").read_bytes()
    obs = parse_nmap_xml(xml)
    # runstats present with no hosts: it's a valid (empty) result, not a failure.
    assert obs["status"] == "success"
    assert obs["structured_data"]["hosts"] == []


def test_parse_nmap_xml_malformed_input():
    obs = parse_nmap_xml(b"not xml at all")
    assert obs["status"] == "failure"
    assert obs["errors"]


def test_parse_nmap_xml_empty_input():
    obs = parse_nmap_xml(b"")
    assert obs["status"] == "failure"
