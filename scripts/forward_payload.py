import os
import json
import threading
import requests
import enum
import base64
import io
import numpy as np
import cv2
from PIL import Image
from typing import Any, Dict, List
import modules.scripts as scripts
import gradio as gr
from modules import shared, script_callbacks
from modules.api.models import (
    StableDiffusionImg2ImgProcessingAPI,
    StableDiffusionTxt2ImgProcessingAPI,
)
from modules.processing import (
    StableDiffusionProcessing,
    StableDiffusionProcessingImg2Img,
)

BASE64_IMAGE_PLACEHOLDER = "base64image placeholder"

def pil_to_base64(pil_img: Image.Image) -> str:
    iobuf = io.BytesIO()
    pil_img.save(iobuf, format="png")
    binary_img = iobuf.getvalue()
    base64_img = base64.b64encode(binary_img)
    return base64_img.decode("utf-8")

def img_to_base64(img: np.ndarray) -> str:
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    return pil_to_base64(pil_img)

def make_json_compatible(value: Any) -> Any:
    def is_jsonable(x):
        try:
            json.dumps(x, allow_nan=False)
            return True
        except (TypeError, OverflowError, ValueError):
            return False

    if is_jsonable(value):
        return value
    if isinstance(value, dict):
        return {k: make_json_compatible(v) for k, v in value.items()}
    if any(isinstance(value, t) for t in (set, list, tuple)):
        return [make_json_compatible(v) for v in value]
    if isinstance(value, enum.Enum):
        return make_json_compatible(value.value)
    if isinstance(value, np.ndarray):
        return img_to_base64(value)
    if isinstance(value, Image.Image):
        return pil_to_base64(value)
    if hasattr(value, "__dict__"):
        return make_json_compatible(vars(value))
    if value in (float("inf"), float("-inf")):
        return None
    return None

def selectable_script_payload(p: StableDiffusionProcessing) -> Dict:
    script_runner: scripts.ScriptRunner = p.scripts
    selectable_script_index = p.script_args[0]
    if selectable_script_index == 0:
        return {"script_name": None, "script_args": []}
    selectable_script: scripts.Script = script_runner.selectable_scripts[
        selectable_script_index - 1
    ]
    title = selectable_script.title()
    return {
        "script_name": title.lower()
        if title
        else os.path.basename(selectable_script.filename).lower(),
        "script_args": p.script_args[
            selectable_script.args_from : selectable_script.args_to
        ],
    }

def alwayson_script_payload(p: StableDiffusionProcessing) -> Dict:
    script_runner: scripts.ScriptRunner = p.scripts
    all_scripts: Dict[str, List] = {}
    for alwayson_script in script_runner.alwayson_scripts:
        title = alwayson_script.title()
        all_scripts[
            title.lower()
            if title
            else os.path.basename(alwayson_script.filename).lower()
        ] = {"args": p.script_args[alwayson_script.args_from : alwayson_script.args_to]}
    return {"alwayson_scripts": all_scripts}

def seed_enable_extras_payload(p: StableDiffusionProcessing) -> Dict:
    return {
        "seed_enable_extras": not (
            p.subseed == -1
            and p.subseed_strength == 0
            and p.seed_resize_from_h == 0
            and p.seed_resize_from_w == 0
        )
    }

def api_payload_dict(
    p: StableDiffusionProcessing, api_request: Any
) -> Dict:
    excluded_params = [
        "firstphase_width",
        "firstphase_height",
        "sampler_index",
        "send_images",
        "save_images",
    ]
    result = {}
    result.update(selectable_script_payload(p))
    result.update(alwayson_script_payload(p))
    result.update(seed_enable_extras_payload(p))

    # Compatibility for Pydantic v1 (WebUI) and v2 (Forge)
    if hasattr(api_request, "model_fields"):
        fields = api_request.model_fields.keys()
    elif hasattr(api_request, "__fields__"):
        fields = api_request.__fields__.keys()
    else:
        fields = []

    for name in fields:
        if name in result or name in excluded_params:
            continue
        if not hasattr(p, name):
            continue
        value = getattr(p, name)
        if value is None:
            continue
        if isinstance(p, StableDiffusionProcessingImg2Img) and name == "init_images":
            if isinstance(value, list):
                value = [make_json_compatible(v) for v in value]
            else:
                value = [BASE64_IMAGE_PLACEHOLDER]
        result[name] = value
    return make_json_compatible(result)

def send_payload(url: str, payload: Dict):
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[ForwardPayload] Successfully forwarded payload to {url}")
        else:
            print(
                f"[ForwardPayload] Failed to forward payload to {url}. Status code: {response.status_code}"
            )
    except Exception as e:
        print(f"[ForwardPayload] Error forwarding payload to {url}: {e}")

def on_ui_settings():
    section = ("forward_payload", "Forward Payload")
    shared.opts.add_option(
        "forward_payload_enabled",
        shared.OptionInfo(
            False,
            "Enable Forward Payload",
            gr.Checkbox,
            {"interactive": True},
            section=section,
        ),
    )
    shared.opts.add_option(
        "forward_payload_base_url",
        shared.OptionInfo(
            "",
            "Target Base URL (e.g., http://127.0.0.1:7860). Overridden by SD_FORWARD_PAYLOAD_URL env var if set.",
            gr.Textbox,
            {"interactive": True},
            section=section,
        ),
    )

script_callbacks.on_ui_settings(on_ui_settings)

class ForwardPayloadScript(scripts.Script):
    def title(self):
        return "Forward Payload"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        return []

    def process(self, p: StableDiffusionProcessing, *args):
        # Environment variable takes precedence for enabling and URL
        env_url = os.environ.get("SD_FORWARD_PAYLOAD_URL")
        enabled = shared.opts.data.get("forward_payload_enabled", False)

        if env_url:
            enabled = True
            base_url = env_url
        else:
            base_url = shared.opts.data.get("forward_payload_base_url", "")

        if not enabled or not base_url:
            return

        # Ensure base_url has a schema
        if not base_url.startswith(("http://", "https://")):
            base_url = "http://" + base_url

        # Remove trailing slash
        base_url = base_url.rstrip("/")

        is_img2img = isinstance(p, StableDiffusionProcessingImg2Img)

        # Only forward if txt2img
        if is_img2img:
            return

        endpoint = "/sdapi/v1/txt2img"
        target_url = base_url + endpoint

        api_request = StableDiffusionTxt2ImgProcessingAPI

        try:
            payload = api_payload_dict(p, api_request)
            payload["seed"] = -1

            threading.Thread(
                target=send_payload, args=(target_url, payload), daemon=True
            ).start()

        except Exception as e:
            print(f"[ForwardPayload] Error preparing payload: {e}")
