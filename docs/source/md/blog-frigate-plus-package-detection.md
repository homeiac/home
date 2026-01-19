# Frigate+ and Package Detection: What I Learned About Edge TPU Models

*Demystifying how Frigate loads models onto Coral TPU - it's simpler than you think*

---

## The Question That Wouldn't Die

"How does Frigate install the model on the Coral TPU?"

I kept asking this question, expecting some complex flashing procedure, some firmware update ritual, some arcane incantation to bless the silicon. The answer turned out to be beautifully mundane.

**It doesn't install anything.** The model loads into the TPU's memory fresh on every inference.

## How Edge TPU Actually Works

The Google Coral Edge TPU is not like a GPU with persistent memory or firmware you flash. It's more like a specialized calculator:

1. **Model file sits on disk** - A `.tflite` file, quantized to INT8, compiled for Edge TPU
2. **Frigate starts** - Loads the model file into TPU memory via the Edge TPU runtime
3. **Inference happens** - Image goes in, detections come out
4. **Repeat** - The model stays in TPU memory until the process stops

When you change models (like switching to Frigate+), Frigate simply loads a different `.tflite` file on next startup. No flashing. No installation. Just a different file.

## The Frigate+ Model Loading Flow

Here's what actually happens when you configure `model: path: plus://c7b38453...`:

```
1. Frigate starts
2. Sees plus:// URL in config
3. Checks /config/model_cache/ for cached model
4. If missing: downloads from Frigate+ API (requires PLUS_API_KEY)
5. Caches to /config/model_cache/c7b38453...
6. Also downloads .json with model metadata (labels, dimensions)
7. Loads model into Edge TPU memory
8. Ready for inference
```

The model cache persists across restarts. Frigate only downloads once, then uses the cached file.

## What's In The Model File?

I checked the Frigate+ model config after it downloaded:

```json
{
  "id": "c7b38453956cda87076baba4aca213e6",
  "name": "mobiledet",
  "isBaseModel": true,
  "supportedDetectors": ["edgetpu"],
  "width": 320,
  "height": 320,
  "labelMap": {
    "0": "person",
    "5": "package",
    "21": "usps",
    "22": "ups",
    "23": "amazon",
    "25": "fedex",
    "29": "car",
    ...40 total labels...
  }
}
```

The key insight: **the model itself contains the knowledge of what a "package" looks like**. The label map just gives names to the output classes. All the actual detection smarts are baked into the 4.8MB `.tflite` file.

## Why Frigate+ Over Free Model?

The free model bundled with Frigate uses a standard COCO-trained MobileDet. It knows:
- person, car, bicycle, motorcycle, bus, truck
- dog, cat, bird, horse, sheep, cow
- Standard COCO objects

It does NOT know:
- package
- amazon/ups/fedex/usps logos
- waste_bin, robot_lawnmower
- delivery-specific objects

Frigate+ models are trained on **security camera footage submitted by users**. They've seen thousands of packages on porches, in various lighting, at various angles. The free model has never seen a package in its training data.

## The Fine-Tuning Question

Should you fine-tune for your specific setup?

**Yes, especially for packages.** Here's why:

1. **Your camera angle is unique** - Base model trained on everyone's cameras, not yours
2. **Your packages vary** - Amazon boxes, padded envelopes, grocery bags
3. **Your environment** - Lighting, shadows, porch furniture that might look like packages

The workflow:
1. Run base model for 1-2 weeks
2. Review detections in Frigate UI → Explore tab
3. Submit true positives and false positives to Frigate+
4. Request fine-tuned model (uses 1 of 12 annual trainings)
5. New model trained on YOUR camera's images

## Cost Analysis

Frigate+ is $50/year. You get:
- Base models with package detection (keep forever, even after canceling)
- 12 fine-tuning sessions per year
- New base models quarterly (only while subscribed)

If you cancel after year one, you keep your downloaded models. They don't phone home. They don't expire. The model file is yours.

Is it worth $50 for package detection? For a doorbell camera, absolutely. Missing a package theft costs more than $50.

## Configuration

The actual config is trivial:

```yaml
# In frigate config.yml

model:
  path: plus://c7b38453956cda87076baba4aca213e6

detectors:
  coral:
    type: edgetpu
    device: usb

cameras:
  doorbell:
    objects:
      track:
        - person
        - car
        - package  # Now works!
```

Set `PLUS_API_KEY` environment variable (I added it to K8s secret), restart Frigate, done.

## Verification

After restart, check the model loaded:

```bash
# Model cached?
ls /config/model_cache/
# c7b38453956cda87076baba4aca213e6
# c7b38453956cda87076baba4aca213e6.json

# Detection working?
curl frigate/api/stats | jq '.detectors'
# {"coral": {"inference_speed": 24.8, "pid": 405}}
```

24.8ms inference on Coral USB. Same speed as free model - the TPU doesn't care what labels the model outputs.

## Key Takeaways

1. **No TPU flashing required** - Models load into memory on startup, not burned into firmware
2. **Model files are portable** - Download once, cache forever, keep after canceling
3. **Edge TPU only runs specific models** - Must be INT8 quantized, compiled for Edge TPU
4. **Frigate+ is the easy path** - They handle the model training and Edge TPU compilation
5. **Fine-tuning is worth it** - Your camera, your packages, your model

---

*The doorbell now watches for packages. Somewhere, a Coral TPU runs 24ms inferences, blissfully unaware of the confusion its simple "load model, run inference" architecture caused. Sometimes the simplest answers are the hardest to accept.*

---

**Tags:** frigate, frigate-plus, coral, edge-tpu, google-coral, package-detection, machine-learning, tflite, object-detection, home-assistant, nvr, doorbell, homelab

**Related:** [Frigate Reolink Configuration](/docs/frigate-reolink), [Coral TPU Setup](/docs/coral-setup)
