#!/usr/bin/env python3
"""
Frigate Camera IP Webhook
Receives camera IP updates from Home Assistant and patches the Frigate ConfigMap.
Triggers a Frigate pod restart via annotation update.
"""
import os
import re
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from kubernetes import client, config

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

NAMESPACE = os.environ.get("FRIGATE_NAMESPACE", "frigate")
CONFIGMAP_NAME = os.environ.get("FRIGATE_CONFIGMAP", "frigate-config")
DEPLOYMENT_NAME = os.environ.get("FRIGATE_DEPLOYMENT", "frigate")

# Camera config: maps friendly name to config paths that need IP replacement
CAMERA_CONFIG = {
    "living_room": {
        "go2rtc_streams": ["living_room_main", "living_room_sub"],
        "onvif_camera": "living_room",
    },
    "hall": {
        "go2rtc_streams": ["hall_main", "hall_sub"],
        "onvif_camera": "hall",
    },
}


def get_k8s_client():
    """Initialize Kubernetes client."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api(), client.AppsV1Api()


def update_configmap_ips(camera_ips: dict) -> tuple[bool, str]:
    """
    Update camera IPs in the Frigate ConfigMap.

    Args:
        camera_ips: Dict mapping camera name to new IP, e.g. {"living_room": "192.168.1.138"}

    Returns:
        (success, message)
    """
    v1, apps_v1 = get_k8s_client()

    try:
        # Get current ConfigMap
        cm = v1.read_namespaced_config_map(name=CONFIGMAP_NAME, namespace=NAMESPACE)
        config_yaml = cm.data.get("config.yml", "")

        if not config_yaml:
            return False, "ConfigMap has no config.yml"

        original_config = config_yaml
        changes = []

        for camera_name, new_ip in camera_ips.items():
            if camera_name not in CAMERA_CONFIG:
                logger.warning(f"Unknown camera: {camera_name}")
                continue

            cam_config = CAMERA_CONFIG[camera_name]

            # Update go2rtc stream URLs
            # Pattern: @OLD_IP:554/ -> @NEW_IP:554/
            for stream_name in cam_config.get("go2rtc_streams", []):
                # Match the stream line and capture the IP
                pattern = rf'({stream_name}:.*?@)(\d+\.\d+\.\d+\.\d+)(:\d+/)'
                match = re.search(pattern, config_yaml)
                if match:
                    old_ip = match.group(2)
                    if old_ip != new_ip:
                        config_yaml = re.sub(pattern, rf'\g<1>{new_ip}\g<3>', config_yaml)
                        changes.append(f"{stream_name}: {old_ip} -> {new_ip}")

            # Update ONVIF host
            onvif_camera = cam_config.get("onvif_camera")
            if onvif_camera:
                # Match: cameras: ... camera_name: ... onvif: ... host: IP
                # This is tricky with YAML, so we use a simpler pattern
                # Look for "host: IP" after the camera section
                # Pattern finds: host: OLD_IP in the onvif section
                pattern = rf'(onvif:\s+host:\s+)(\d+\.\d+\.\d+\.\d+)'

                # We need to be more specific - find the camera block first
                # For now, use a global replace since IPs are unique per camera
                for match in re.finditer(pattern, config_yaml):
                    old_ip = match.group(2)
                    # Only replace if this IP belongs to this camera
                    # Check context around the match
                    start = max(0, match.start() - 200)
                    context = config_yaml[start:match.start()]
                    if camera_name in context or onvif_camera in context:
                        if old_ip != new_ip:
                            # Replace just this occurrence
                            config_yaml = config_yaml[:match.start()] + \
                                         match.group(1) + new_ip + \
                                         config_yaml[match.end():]
                            changes.append(f"{onvif_camera} onvif: {old_ip} -> {new_ip}")
                            break

        if not changes:
            return True, "No changes needed - IPs already match"

        # Update ConfigMap
        cm.data["config.yml"] = config_yaml
        v1.patch_namespaced_config_map(
            name=CONFIGMAP_NAME,
            namespace=NAMESPACE,
            body={"data": cm.data}
        )

        logger.info(f"ConfigMap updated: {changes}")

        # Trigger Frigate restart by updating deployment annotation
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "camera-ips-updated": datetime.utcnow().isoformat()
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE,
            body=patch
        )
        logger.info("Frigate deployment restart triggered")

        return True, f"Updated: {', '.join(changes)}"

    except client.exceptions.ApiException as e:
        logger.error(f"Kubernetes API error: {e}")
        return False, f"K8s API error: {e.reason}"
    except Exception as e:
        logger.error(f"Error updating ConfigMap: {e}")
        return False, str(e)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


@app.route("/update", methods=["POST"])
def update_ips():
    """
    Update camera IPs endpoint.

    Expected JSON body:
    {
        "living_room": "192.168.1.138",
        "hall": "192.168.1.137"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body provided"}), 400

        logger.info(f"Received IP update request: {data}")

        # Filter to only known cameras
        camera_ips = {k: v for k, v in data.items() if k in CAMERA_CONFIG}

        if not camera_ips:
            return jsonify({"error": "No valid camera names in request"}), 400

        success, message = update_configmap_ips(camera_ips)

        if success:
            return jsonify({"status": "success", "message": message})
        else:
            return jsonify({"status": "error", "message": message}), 500

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/current", methods=["GET"])
def get_current_ips():
    """Get current camera IPs from ConfigMap."""
    v1, _ = get_k8s_client()

    try:
        cm = v1.read_namespaced_config_map(name=CONFIGMAP_NAME, namespace=NAMESPACE)
        config_yaml = cm.data.get("config.yml", "")

        ips = {}
        for camera_name, cam_config in CAMERA_CONFIG.items():
            # Extract IP from first stream
            stream_name = cam_config.get("go2rtc_streams", [""])[0]
            if stream_name:
                pattern = rf'{stream_name}:.*?@(\d+\.\d+\.\d+\.\d+):\d+/'
                match = re.search(pattern, config_yaml)
                if match:
                    ips[camera_name] = match.group(1)

        return jsonify({"cameras": ips})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Frigate IP Webhook on port {port}")
    app.run(host="0.0.0.0", port=port)
