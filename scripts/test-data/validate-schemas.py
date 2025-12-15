#!/usr/bin/env python3
"""
JSON Schema validator for MQTT messages.

Validates messages against schemas in the schemas/ directory.
Can validate from file, stdin, or subscribe to MQTT broker.

Usage:
    python validate-schemas.py --file message.json --schema claude-status
    python validate-schemas.py --broker mqtt.homelab --subscribe "claude/#"
    cat message.json | python validate-schemas.py --schema claude-status
    python validate-schemas.py --validate-all  # Validate all examples in schemas
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Optional

try:
    import jsonschema
    from jsonschema import validate, ValidationError, SchemaError
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)

# Schema directory relative to this script
SCRIPT_DIR = Path(__file__).parent
SCHEMA_DIR = SCRIPT_DIR.parent.parent / "schemas"

# Topic to schema mapping
TOPIC_SCHEMA_MAP = {
    "claude/home/status": "claude-status",
    "claude/work/status": "claude-status",
    "claude/home/task/": "claude-task",  # prefix match
    "claude/work/task/": "claude-task",
    "claude/home/notification": "claude-notification",
    "claude/work/notification": "claude-notification",
    "claude/command": "claude-command",
    "presence/": "presence-detected",  # prefix match
}


def load_schema(schema_name: str) -> dict:
    """Load a JSON schema by name."""
    schema_file = SCHEMA_DIR / f"{schema_name}.schema.json"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema not found: {schema_file}")

    with open(schema_file) as f:
        return json.load(f)


def get_schema_for_topic(topic: str) -> Optional[str]:
    """Determine which schema to use for a given MQTT topic."""
    # Exact match first
    if topic in TOPIC_SCHEMA_MAP:
        return TOPIC_SCHEMA_MAP[topic]

    # Prefix match
    for prefix, schema in TOPIC_SCHEMA_MAP.items():
        if prefix.endswith("/") and topic.startswith(prefix):
            return schema

    return None


def validate_message(message: dict, schema_name: str, topic: str = None) -> tuple[bool, str]:
    """
    Validate a message against a schema.
    Returns (is_valid, error_message).
    """
    try:
        schema = load_schema(schema_name)
        validate(instance=message, schema=schema)
        return True, ""
    except ValidationError as e:
        path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        return False, f"Validation failed at '{path}': {e.message}"
    except SchemaError as e:
        return False, f"Schema error: {e.message}"
    except FileNotFoundError as e:
        return False, str(e)


def validate_file(filepath: str, schema_name: str) -> bool:
    """Validate a JSON file against a schema."""
    try:
        with open(filepath) as f:
            message = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {filepath}: {e}")
        return False
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        return False

    is_valid, error = validate_message(message, schema_name)
    if is_valid:
        print(f"OK: {filepath} validates against {schema_name}")
        return True
    else:
        print(f"FAIL: {filepath}: {error}")
        return False


def validate_examples() -> bool:
    """Validate all examples embedded in schema files."""
    print("Validating schema examples...\n")
    all_valid = True

    for schema_file in SCHEMA_DIR.glob("*.schema.json"):
        schema_name = schema_file.stem.replace(".schema", "")
        print(f"Schema: {schema_name}")

        try:
            schema = load_schema(schema_name)
        except Exception as e:
            print(f"  ERROR loading schema: {e}")
            all_valid = False
            continue

        examples = schema.get("examples", [])
        if not examples:
            print("  (no examples)")
            continue

        for i, example in enumerate(examples):
            is_valid, error = validate_message(example, schema_name)
            if is_valid:
                print(f"  Example {i+1}: OK")
            else:
                print(f"  Example {i+1}: FAIL - {error}")
                all_valid = False
        print()

    return all_valid


def mqtt_subscriber(broker: str, topic_pattern: str, verbose: bool = False):
    """Subscribe to MQTT and validate messages in real-time."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
        sys.exit(1)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to {broker}, subscribing to '{topic_pattern}'")
            client.subscribe(topic_pattern)
        else:
            print(f"Connection failed with code {rc}")

    def on_message(client, userdata, msg):
        topic = msg.topic
        schema_name = get_schema_for_topic(topic)

        if not schema_name:
            if verbose:
                print(f"SKIP: {topic} (no schema mapping)")
            return

        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError as e:
            print(f"FAIL: {topic}: Invalid JSON - {e}")
            return

        is_valid, error = validate_message(payload, schema_name)
        if is_valid:
            print(f"OK: {topic} ({schema_name})")
            if verbose:
                print(f"    {json.dumps(payload)[:100]}...")
        else:
            print(f"FAIL: {topic}: {error}")
            print(f"    Payload: {json.dumps(payload)[:200]}")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(broker, 1883, 60)
        print(f"Listening for messages... (Ctrl+C to stop)\n")
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Validate MQTT messages against JSON schemas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --validate-all                          # Validate schema examples
  %(prog)s --file msg.json --schema claude-status  # Validate file
  %(prog)s --broker mqtt.homelab --subscribe "claude/#"  # Live validation
  echo '{"server":"home"...}' | %(prog)s --schema claude-status  # From stdin
        """
    )

    parser.add_argument(
        "--file", "-f",
        help="JSON file to validate"
    )
    parser.add_argument(
        "--schema", "-s",
        help="Schema name (e.g., claude-status, claude-task)"
    )
    parser.add_argument(
        "--broker", "-b",
        help="MQTT broker hostname for live validation"
    )
    parser.add_argument(
        "--subscribe", "-t",
        default="claude/#",
        help="MQTT topic pattern to subscribe to (default: claude/#)"
    )
    parser.add_argument(
        "--validate-all",
        action="store_true",
        help="Validate all examples in schema files"
    )
    parser.add_argument(
        "--list-schemas",
        action="store_true",
        help="List available schemas"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # List schemas
    if args.list_schemas:
        print("Available schemas:\n")
        for schema_file in sorted(SCHEMA_DIR.glob("*.schema.json")):
            name = schema_file.stem.replace(".schema", "")
            print(f"  {name}")
        print(f"\nSchema directory: {SCHEMA_DIR}")
        return

    # Validate all examples
    if args.validate_all:
        success = validate_examples()
        sys.exit(0 if success else 1)

    # MQTT subscription mode
    if args.broker:
        mqtt_subscriber(args.broker, args.subscribe, args.verbose)
        return

    # File validation mode
    if args.file:
        if not args.schema:
            print("ERROR: --schema required when validating file")
            sys.exit(1)
        success = validate_file(args.file, args.schema)
        sys.exit(0 if success else 1)

    # Stdin mode
    if not sys.stdin.isatty():
        if not args.schema:
            print("ERROR: --schema required when reading from stdin")
            sys.exit(1)
        try:
            message = json.load(sys.stdin)
            is_valid, error = validate_message(message, args.schema)
            if is_valid:
                print(f"OK: validates against {args.schema}")
                sys.exit(0)
            else:
                print(f"FAIL: {error}")
                sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON from stdin: {e}")
            sys.exit(1)

    # No input provided
    parser.print_help()


if __name__ == "__main__":
    main()
