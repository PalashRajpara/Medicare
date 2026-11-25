"""Execution run context and time-ordered UUIDv7 generation."""

import os
import time
import uuid


def generate_uuidv7() -> str:
    """Generate time-ordered UUIDv7 string.

    Format: 48-bit timestamp ms, 4-bit version 7, 12-bit random,
    2-bit variant (10), 62-bit random.
    """
    timestamp_ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)

    # 48-bit timestamp
    time_high = (timestamp_ms >> 16) & 0xFFFFFFFF
    time_low = timestamp_ms & 0xFFFF

    # 12-bit random + 4-bit version 7
    rand_a = int.from_bytes(rand_bytes[0:2], "big") & 0x0FFF
    version_and_rand = 0x7000 | rand_a

    # 2-bit variant 10 + 62-bit random
    rand_b = int.from_bytes(rand_bytes[2:10], "big") & 0x3FFFFFFFFFFFFFFF
    variant_and_rand = 0x8000000000000000 | rand_b

    return (
        f"{time_high:08x}-"
        f"{time_low:04x}-"
        f"{version_and_rand:04x}-"
        f"{(variant_and_rand >> 48) & 0xFFFF:04x}-"
        f"{variant_and_rand & 0xFFFFFFFFFFFF:012x}"
    )


class ExecutionContext:
    """Carries request metadata and execution tracing identifiers."""

    def __init__(
        self,
        run_id: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_id: str = "default",
        model: str = "default",
    ) -> None:
        self.run_id = run_id or generate_uuidv7()
        self.thread_id = thread_id or str(uuid.uuid4())
        self.user_id = user_id
        self.agent_id = agent_id
        self.model = model
