#!/usr/bin/env python3
"""
Synthetic data generator for Claude Code Ambient AI testing.

Generates realistic MQTT message sequences for all use cases.
Supports JSON output for verification or direct MQTT publishing.

Usage:
    python generate.py --usecase all                              # All use cases as JSON
    python generate.py --usecase p0_1_ask_claude                  # Single use case
    python generate.py --usecase all --output mqtt --broker mqtt.homelab  # Publish to broker
    python generate.py --list                                     # List available use cases
"""

import json
import random
import argparse
import subprocess
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class Server(Enum):
    HOME = "home"
    WORK = "work"


class TaskEvent(Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


class Priority(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CommandType(Enum):
    CHAT = "chat"
    ACTION = "action"
    ACK = "ack"
    REFRESH = "refresh"


class DeviceSource(Enum):
    VOICE_PE = "voice_pe"
    ATOMS3R = "atoms3r"
    PUCK = "puck"
    CARDPUTER = "cardputer"
    HA_AUTOMATION = "ha_automation"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClaudeStatus:
    """Status message for claude/{server}/status"""
    server: str
    online: bool
    sessions: int
    git_dirty: int
    active_task: Optional[str]
    last_activity: str

    @classmethod
    def healthy_home(cls) -> "ClaudeStatus":
        return cls(
            server="home",
            online=True,
            sessions=2,
            git_dirty=0,
            active_task=None,
            last_activity=datetime.utcnow().isoformat() + "Z"
        )

    @classmethod
    def dirty_repos(cls, count: int = 3) -> "ClaudeStatus":
        return cls(
            server="home",
            online=True,
            sessions=1,
            git_dirty=count,
            active_task="Reviewing changes",
            last_activity=datetime.utcnow().isoformat() + "Z"
        )

    @classmethod
    def work_offline(cls) -> "ClaudeStatus":
        return cls(
            server="work",
            online=False,
            sessions=0,
            git_dirty=0,
            active_task=None,
            last_activity=(datetime.utcnow() - timedelta(hours=8)).isoformat() + "Z"
        )

    @classmethod
    def stale(cls, hours_old: int = 24) -> "ClaudeStatus":
        return cls(
            server="home",
            online=True,
            sessions=1,
            git_dirty=0,
            active_task=None,
            last_activity=(datetime.utcnow() - timedelta(hours=hours_old)).isoformat() + "Z"
        )

    @classmethod
    def busy_home(cls) -> "ClaudeStatus":
        return cls(
            server="home",
            online=True,
            sessions=3,
            git_dirty=2,
            active_task="Running pytest tests/",
            last_activity=datetime.utcnow().isoformat() + "Z"
        )


@dataclass
class TaskMessage:
    """Task event for claude/{server}/task/{task_id}"""
    event: str
    task_id: str
    description: str
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    @classmethod
    def pytest_started(cls) -> "TaskMessage":
        return cls(
            event="started",
            task_id=f"task_{random.randint(1000,9999)}",
            description="Running pytest tests/"
        )

    @classmethod
    def pytest_completed(cls, task_id: str, duration_ms: int = 45000) -> "TaskMessage":
        return cls(
            event="completed",
            task_id=task_id,
            description="pytest tests/ - 42 passed",
            duration_ms=duration_ms
        )

    @classmethod
    def deploy_failed(cls, task_id: str) -> "TaskMessage":
        return cls(
            event="failed",
            task_id=task_id,
            description="kubectl apply -f deployment.yaml",
            duration_ms=30000,
            error="Error: ImagePullBackOff - registry.homelab/app:latest"
        )

    @classmethod
    def git_status_started(cls) -> "TaskMessage":
        return cls(
            event="started",
            task_id=f"task_{random.randint(1000,9999)}",
            description="git status"
        )

    @classmethod
    def git_status_completed(cls, task_id: str) -> "TaskMessage":
        return cls(
            event="completed",
            task_id=task_id,
            description="3 uncommitted files in home repo",
            duration_ms=150
        )


@dataclass
class Notification:
    """Notification for claude/{server}/notification"""
    priority: str
    title: str
    message: str
    actions: List[str] = field(default_factory=lambda: ["dismiss"])
    timestamp: Optional[str] = None
    source: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    @classmethod
    def k8s_critical(cls) -> "Notification":
        return cls(
            priority="critical",
            title="K8s Pod CrashLoopBackOff",
            message="frigate-7f8899f485-jvqqv restarting every 30s",
            actions=["view_logs", "restart_pod", "dismiss"],
            source="kubernetes-monitor"
        )

    @classmethod
    def git_reminder(cls) -> "Notification":
        return cls(
            priority="warning",
            title="Uncommitted changes",
            message="3 files modified in home repo for 2 hours",
            actions=["commit", "stash", "dismiss"]
        )

    @classmethod
    def task_done(cls, task_name: str) -> "Notification":
        return cls(
            priority="info",
            title="Task completed",
            message=f"{task_name} finished successfully",
            actions=["dismiss"]
        )

    @classmethod
    def unknown_person(cls) -> "Notification":
        return cls(
            priority="critical",
            title="Unknown person detected",
            message="Unrecognized person at front door",
            actions=["view_camera", "dismiss"],
            source="frigate"
        )


@dataclass
class PresenceEvent:
    """Presence detection for presence/{device}/detected"""
    person: str
    confidence: float
    camera: str
    timestamp: str
    frigate_event_id: Optional[str] = None
    thumbnail_url: Optional[str] = None

    @classmethod
    def family_member(cls, name: str = "G") -> "PresenceEvent":
        return cls(
            person=name,
            confidence=0.95,
            camera="living_room",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    @classmethod
    def unknown_person(cls) -> "PresenceEvent":
        event_id = f"{int(datetime.utcnow().timestamp())}.{random.randint(100,999)}"
        return cls(
            person="unknown",
            confidence=0.78,
            camera="front_door",
            timestamp=datetime.utcnow().isoformat() + "Z",
            frigate_event_id=event_id,
            thumbnail_url=f"http://frigate.homelab/api/events/{event_id}/thumbnail.jpg"
        )


@dataclass
class Command:
    """Command for claude/command"""
    source: str
    server: str
    type: str
    message: Optional[str] = None
    action: Optional[str] = None
    task_id: Optional[str] = None
    notification_id: Optional[str] = None

    @classmethod
    def voice_chat(cls, message: str) -> "Command":
        return cls(
            source="voice_pe",
            server="home",
            type="chat",
            message=message
        )

    @classmethod
    def puck_refresh(cls) -> "Command":
        return cls(
            source="puck",
            server="home",
            type="refresh"
        )

    @classmethod
    def puck_ack(cls, task_id: str) -> "Command":
        return cls(
            source="puck",
            server="home",
            type="ack",
            task_id=task_id
        )

    @classmethod
    def cardputer_command(cls, message: str) -> "Command":
        return cls(
            source="cardputer",
            server="home",
            type="chat",
            message=message
        )

    @classmethod
    def atoms3r_chat(cls, message: str) -> "Command":
        return cls(
            source="atoms3r",
            server="home",
            type="chat",
            message=message
        )


@dataclass
class Response:
    """Response for claude/{server}/response"""
    response: str
    tts: bool = True
    task_id: Optional[str] = None


@dataclass
class SpeakCommand:
    """Speak command for {device}/speak"""
    message: str
    priority: str = "normal"


# =============================================================================
# USE CASE DATA SEQUENCES
# =============================================================================

def usecase_p0_1_ask_claude() -> List[dict]:
    """P0-1: Ask Claude from anywhere (voice)"""
    task = TaskMessage.git_status_started()
    return [
        {
            "topic": "claude/command",
            "payload": asdict(Command.voice_chat("what is the git status?")),
            "description": "Voice PE sends question"
        },
        {
            "topic": f"claude/home/task/{task.task_id}",
            "payload": asdict(task),
            "description": "Task started"
        },
        {
            "topic": f"claude/home/task/{task.task_id}",
            "payload": asdict(TaskMessage.git_status_completed(task.task_id)),
            "description": "Task completed"
        },
        {
            "topic": "claude/home/response",
            "payload": asdict(Response(
                response="You have 3 uncommitted files in the home repo: CLAUDE.md, scripts/test.sh, and docs/plan.md",
                tts=True,
                task_id=task.task_id
            )),
            "description": "Response for TTS"
        },
    ]


def usecase_p0_2_task_complete() -> List[dict]:
    """P0-2: Know when Claude is done"""
    task = TaskMessage.pytest_started()
    return [
        {
            "topic": f"claude/home/task/{task.task_id}",
            "payload": asdict(task),
            "description": "pytest started"
        },
        {
            "topic": f"claude/home/task/{task.task_id}",
            "payload": asdict(TaskMessage.pytest_completed(task.task_id, 45230)),
            "description": "pytest completed after 45s"
        },
        {
            "topic": "claude/home/notification",
            "payload": asdict(Notification.task_done("pytest tests/")),
            "description": "Completion notification"
        },
    ]


def usecase_p0_2_task_failed() -> List[dict]:
    """P0-2 variant: Task fails"""
    task_id = f"task_{random.randint(1000,9999)}"
    return [
        {
            "topic": f"claude/home/task/{task_id}",
            "payload": asdict(TaskMessage(
                event="started",
                task_id=task_id,
                description="kubectl apply -f deployment.yaml"
            )),
            "description": "Deploy started"
        },
        {
            "topic": f"claude/home/task/{task_id}",
            "payload": asdict(TaskMessage.deploy_failed(task_id)),
            "description": "Deploy failed"
        },
        {
            "topic": "claude/home/notification",
            "payload": asdict(Notification(
                priority="critical",
                title="Deploy failed",
                message="ImagePullBackOff - registry.homelab/app:latest",
                actions=["retry", "rollback", "dismiss"],
                source=task_id
            )),
            "description": "Failure notification"
        },
    ]


def usecase_p1_3_proactive_briefing() -> List[dict]:
    """P1-3: Proactive briefing on entry"""
    return [
        # Pre-existing state (retained messages)
        {
            "topic": "claude/home/status",
            "payload": asdict(ClaudeStatus.dirty_repos(2)),
            "retain": True,
            "description": "Retained: 2 dirty repos"
        },
        {
            "topic": "claude/home/notification",
            "payload": asdict(Notification.k8s_critical()),
            "retain": True,
            "description": "Retained: K8s critical alert"
        },
        # Trigger: person detected
        {
            "topic": "frigate/events",
            "payload": {
                "type": "new",
                "after": {
                    "id": f"{int(datetime.utcnow().timestamp())}.123",
                    "camera": "living_room",
                    "label": "person",
                    "sub_label": "G"
                }
            },
            "description": "Frigate detects person"
        },
        {
            "topic": "presence/atoms3r/detected",
            "payload": asdict(PresenceEvent.family_member("G")),
            "description": "AtomS3R confirms G"
        },
        # Response: briefing spoken
        {
            "topic": "atoms3r/speak",
            "payload": asdict(SpeakCommand(
                message="Welcome back. You have 2 uncommitted files, and there's a critical K8s alert: frigate pod is crash looping.",
                priority="high"
            )),
            "description": "Briefing spoken via AtomS3R"
        },
    ]


def usecase_p1_5_glanceable_status() -> List[dict]:
    """P1-5: Glanceable status (Puck)"""
    return [
        {
            "topic": "claude/home/status",
            "payload": asdict(ClaudeStatus.healthy_home()),
            "retain": True,
            "description": "Home server healthy"
        },
        {
            "topic": "claude/work/status",
            "payload": asdict(ClaudeStatus.work_offline()),
            "retain": True,
            "description": "Work server offline"
        },
    ]


def usecase_p1_5_puck_interaction() -> List[dict]:
    """P1-5 variant: User interacts with Puck"""
    return [
        {
            "topic": "claude/home/status",
            "payload": asdict(ClaudeStatus.busy_home()),
            "retain": True,
            "description": "Initial status"
        },
        {
            "topic": "claude/command",
            "payload": asdict(Command.puck_refresh()),
            "description": "User presses refresh"
        },
        {
            "topic": "claude/home/status",
            "payload": asdict(ClaudeStatus.healthy_home()),
            "retain": True,
            "description": "Updated status"
        },
    ]


def usecase_p2_6_unknown_person() -> List[dict]:
    """P2-6: Unknown person alert"""
    presence = PresenceEvent.unknown_person()
    return [
        {
            "topic": "frigate/events",
            "payload": {
                "type": "new",
                "after": {
                    "id": presence.frigate_event_id,
                    "camera": "front_door",
                    "label": "person",
                    "sub_label": None
                }
            },
            "description": "Frigate detects unknown person"
        },
        {
            "topic": "presence/atoms3r/detected",
            "payload": asdict(presence),
            "description": "AtomS3R cannot identify"
        },
        {
            "topic": "claude/home/notification",
            "payload": asdict(Notification.unknown_person()),
            "description": "Security alert"
        },
    ]


def usecase_p3_8_cardputer_text() -> List[dict]:
    """P3-8: Quick text pager (Cardputer)"""
    task_id = f"task_{random.randint(1000,9999)}"
    return [
        {
            "topic": "claude/command",
            "payload": asdict(Command.cardputer_command("deploy frigate to k8s")),
            "description": "User types command on Cardputer"
        },
        {
            "topic": "claude/home/response",
            "payload": asdict(Response(
                response="Starting Frigate deployment to K8s cluster...",
                tts=False
            )),
            "description": "Acknowledgment (no TTS for Cardputer)"
        },
        {
            "topic": f"claude/home/task/{task_id}",
            "payload": asdict(TaskMessage(
                event="started",
                task_id=task_id,
                description="kubectl apply -f frigate/"
            )),
            "description": "Deploy task started"
        },
    ]


def usecase_failure_malformed_json() -> List[dict]:
    """Failure: Malformed JSON handling"""
    return [
        {
            "topic": "claude/home/status",
            "payload_raw": '{"server":"home", BROKEN JSON HERE',
            "description": "Malformed JSON - device must not crash"
        },
    ]


def usecase_failure_stale_data() -> List[dict]:
    """Failure: Stale retained message"""
    return [
        {
            "topic": "claude/home/status",
            "payload": asdict(ClaudeStatus.stale(hours_old=48)),
            "retain": True,
            "description": "48-hour old retained message"
        },
    ]


def usecase_failure_work_offline() -> List[dict]:
    """Failure: Work server offline"""
    return [
        {
            "topic": "claude/work/status",
            "payload": asdict(ClaudeStatus.work_offline()),
            "retain": True,
            "description": "Work server unavailable"
        },
    ]


def usecase_failure_missing_field() -> List[dict]:
    """Failure: Message missing required field"""
    return [
        {
            "topic": "claude/home/status",
            "payload": {
                "server": "home",
                "online": True,
                # Missing: sessions, git_dirty, last_activity
            },
            "description": "Missing required fields - should be rejected"
        },
    ]


def usecase_multi_device_notification() -> List[dict]:
    """Multi-device: All devices receive critical notification"""
    return [
        {
            "topic": "claude/home/notification",
            "payload": asdict(Notification.k8s_critical()),
            "description": "Critical alert to all devices"
        },
        # Expected device responses (for verification)
        {
            "topic": "puck/ack",
            "payload": {"notification_id": "k8s_crash", "action": "displayed"},
            "description": "Puck acknowledges display"
        },
        {
            "topic": "voice_pe/ack",
            "payload": {"notification_id": "k8s_crash", "action": "spoken"},
            "description": "Voice PE acknowledges TTS"
        },
    ]


# =============================================================================
# REGISTRY
# =============================================================================

ALL_USECASES = {
    "p0_1_ask_claude": {
        "fn": usecase_p0_1_ask_claude,
        "description": "P0-1: Ask Claude from anywhere (voice command)",
        "priority": "P0"
    },
    "p0_2_task_complete": {
        "fn": usecase_p0_2_task_complete,
        "description": "P0-2: Know when Claude is done (success)",
        "priority": "P0"
    },
    "p0_2_task_failed": {
        "fn": usecase_p0_2_task_failed,
        "description": "P0-2: Know when Claude is done (failure)",
        "priority": "P0"
    },
    "p1_3_proactive_briefing": {
        "fn": usecase_p1_3_proactive_briefing,
        "description": "P1-3: Proactive briefing on room entry",
        "priority": "P1"
    },
    "p1_5_glanceable_status": {
        "fn": usecase_p1_5_glanceable_status,
        "description": "P1-5: Glanceable status (initial state)",
        "priority": "P1"
    },
    "p1_5_puck_interaction": {
        "fn": usecase_p1_5_puck_interaction,
        "description": "P1-5: Puck user interaction (refresh)",
        "priority": "P1"
    },
    "p2_6_unknown_person": {
        "fn": usecase_p2_6_unknown_person,
        "description": "P2-6: Unknown person security alert",
        "priority": "P2"
    },
    "p3_8_cardputer_text": {
        "fn": usecase_p3_8_cardputer_text,
        "description": "P3-8: Quick text pager (Cardputer)",
        "priority": "P3"
    },
    "failure_malformed_json": {
        "fn": usecase_failure_malformed_json,
        "description": "Failure: Device handles malformed JSON",
        "priority": "Failure"
    },
    "failure_stale_data": {
        "fn": usecase_failure_stale_data,
        "description": "Failure: Device handles stale retained message",
        "priority": "Failure"
    },
    "failure_work_offline": {
        "fn": usecase_failure_work_offline,
        "description": "Failure: Work server offline handling",
        "priority": "Failure"
    },
    "failure_missing_field": {
        "fn": usecase_failure_missing_field,
        "description": "Failure: Message missing required field",
        "priority": "Failure"
    },
    "multi_device_notification": {
        "fn": usecase_multi_device_notification,
        "description": "Multi-device: Critical notification to all",
        "priority": "Integration"
    },
}


# =============================================================================
# OUTPUT FUNCTIONS
# =============================================================================

def output_json(messages: List[dict], usecase_name: str):
    """Output messages as JSON to stdout"""
    print(f"\n# === {usecase_name} ===")
    for msg in messages:
        print(json.dumps(msg, indent=2, default=str))


def output_mqtt(messages: List[dict], broker: str, usecase_name: str):
    """Publish messages to MQTT broker using mosquitto_pub"""
    print(f"\n# === Publishing: {usecase_name} ===")
    for msg in messages:
        topic = msg["topic"]
        retain = "-r" if msg.get("retain") else ""

        if "payload_raw" in msg:
            payload = msg["payload_raw"]
        else:
            payload = json.dumps(msg["payload"], default=str)

        cmd = f"mosquitto_pub -h {broker} -t '{topic}' {retain} -m '{payload}'"
        print(f"  {msg.get('description', topic)}")
        print(f"    $ {cmd}")

        # Actually run the command
        try:
            subprocess.run(
                ["mosquitto_pub", "-h", broker, "-t", topic] +
                (["-r"] if msg.get("retain") else []) +
                ["-m", payload],
                check=True,
                capture_output=True
            )
            print("    OK")
        except subprocess.CalledProcessError as e:
            print(f"    FAILED: {e.stderr.decode() if e.stderr else str(e)}")
        except FileNotFoundError:
            print("    ERROR: mosquitto_pub not found. Install mosquitto-clients.")
            break


def output_shell(messages: List[dict], broker: str, usecase_name: str):
    """Output mosquitto_pub commands (without executing)"""
    print(f"\n# === {usecase_name} ===")
    for msg in messages:
        topic = msg["topic"]
        retain = "-r" if msg.get("retain") else ""

        if "payload_raw" in msg:
            payload = msg["payload_raw"]
        else:
            payload = json.dumps(msg["payload"], default=str)

        # Escape single quotes in payload for shell
        payload_escaped = payload.replace("'", "'\"'\"'")
        print(f"# {msg.get('description', '')}")
        print(f"mosquitto_pub -h {broker} -t '{topic}' {retain} -m '{payload_escaped}'")
        print()


def list_usecases():
    """List all available use cases"""
    print("\nAvailable use cases:\n")
    current_priority = None
    for name, info in ALL_USECASES.items():
        if info["priority"] != current_priority:
            current_priority = info["priority"]
            print(f"\n## {current_priority}")
        print(f"  {name}")
        print(f"    {info['description']}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic MQTT data for Claude Code Ambient AI testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                                    # List all use cases
  %(prog)s --usecase all                             # All use cases as JSON
  %(prog)s --usecase p0_1_ask_claude                 # Single use case
  %(prog)s --usecase all --output shell              # mosquitto_pub commands
  %(prog)s --usecase all --output mqtt --broker mqtt.homelab  # Publish live
        """
    )
    parser.add_argument(
        "--usecase",
        choices=list(ALL_USECASES.keys()) + ["all"],
        default="all",
        help="Use case to generate data for (default: all)"
    )
    parser.add_argument(
        "--output",
        choices=["json", "mqtt", "shell"],
        default="json",
        help="Output format: json (stdout), mqtt (publish), shell (commands)"
    )
    parser.add_argument(
        "--broker",
        default="mqtt.homelab",
        help="MQTT broker hostname (default: mqtt.homelab)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available use cases and exit"
    )
    parser.add_argument(
        "--priority",
        choices=["P0", "P1", "P2", "P3", "Failure", "Integration"],
        help="Filter by priority level"
    )

    args = parser.parse_args()

    if args.list:
        list_usecases()
        return

    # Determine which use cases to run
    if args.usecase == "all":
        usecases = ALL_USECASES
    else:
        usecases = {args.usecase: ALL_USECASES[args.usecase]}

    # Filter by priority if specified
    if args.priority:
        usecases = {k: v for k, v in usecases.items() if v["priority"] == args.priority}

    # Generate and output data
    for name, info in usecases.items():
        messages = info["fn"]()

        if args.output == "json":
            output_json(messages, name)
        elif args.output == "mqtt":
            output_mqtt(messages, args.broker, name)
        elif args.output == "shell":
            output_shell(messages, args.broker, name)


if __name__ == "__main__":
    main()
