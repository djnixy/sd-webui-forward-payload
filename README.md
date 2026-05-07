# Forward Payload Extension for Stable Diffusion WebUI / Forge

An extension that automatically forwards your `txt2img` generation payloads to a remote server's API when you click the "Generate" button.

## Features

- **Asynchronous Forwarding**: Uses background threads so your local generation isn't delayed.
- **Seed Modification**: Automatically sets the seed to `-1` in the forwarded payload.
- **txt2img Only**: Specifically targets `txt2img` requests and ignores `img2img`.
- **Remote Image Saving**: Option to tell the remote server whether to save the generated images.
- **Hires. fix Conditional Forwarding**: Option to only forward payloads when Hires. fix is enabled (on by default).
- **Payload Inspection**: Automatically saves the forwarded JSON payload to `forwarded_payload.json` for easy inspection.
- **Environment Variable Support**: Configure your target server via `SD_FORWARD_PAYLOAD_URL`.
- **Cross-Platform**: Compatible with both Stable Diffusion WebUI and Forge (supports Pydantic v1 and v2).

## Installation

1. Open Stable Diffusion WebUI or Forge.
2. Go to the **Extensions** tab.
3. Click on **Install from URL**.
4. Paste the URL of this repository.
5. Click **Install**.
6. Restart the UI.

## Configuration

### Via UI
1. Go to the **Settings** tab.
2. Look for the **Forward Payload** section on the left.
3. Set the **Target Base URL** (e.g., `http://192.168.1.100:7860`).
4. (Optional) Configure other settings like **Save generated images on remote server** or **Only forward if Hires. fix is enabled** (both enabled by default).
5. Click **Apply settings**.

### Via Environment Variable
You can set the target URL using the `SD_FORWARD_PAYLOAD_URL` environment variable. This will automatically enable the extension and override any URL set in the UI.

```bash
export SD_FORWARD_PAYLOAD_URL=http://192.168.1.100:7860
```

## How it Works

When you start a `txt2img` generation, the extension captures all the current parameters. It converts them into a JSON structure identical to the standard WebUI API. It then modifies the `seed` to `-1`, adds the `save_images` parameter based on your settings, and sends a POST request to `[Target URL]/sdapi/v1/txt2img` in a background thread.

The extension also saves a copy of the final JSON payload to a file named `forwarded_payload.json` in the extension's root directory every time you generate, which is useful for debugging or replicating requests manually.
