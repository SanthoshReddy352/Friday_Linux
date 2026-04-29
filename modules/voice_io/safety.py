from dataclasses import dataclass


@dataclass
class TranscriptDecision:
    accepted: bool
    reason: str = ""


class VoiceSafetyLayer:
    def __init__(self, max_media_uninvoked_words=4):
        self.max_media_uninvoked_words = max(1, int(max_media_uninvoked_words or 4))

    def evaluate_media_transcript(
        self,
        text,
        *,
        media_active=False,
        media_control_mode=False,
        invoked=False,
        is_media_command=False,
        is_wake_up=False,
        is_bluetooth_active=False,
    ):
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return TranscriptDecision(False, "empty transcript")

        if not media_active and not media_control_mode:
            return TranscriptDecision(True)

        word_count = len(normalized.split())
        if invoked or is_wake_up:
            return TranscriptDecision(True)

        if media_control_mode and is_media_command and word_count <= self.max_media_uninvoked_words:
            return TranscriptDecision(True)

        if word_count > self.max_media_uninvoked_words:
            return TranscriptDecision(False, "long transcript blocked during media")

        if media_active or media_control_mode:
            return TranscriptDecision(False, "media session requires wake word or button")

        return TranscriptDecision(True)
