# Home Assistant integration for Samsung E-Paper (EMDX)

A custom integration to enable basic monitoring of and displaying images on Samsung E-Paper (EMDX) devices.

## Installation

For the best experience, install via [HACS](https://hacs.xyz/).
As this repository is not currently included in the HACS defaults, you'll need to [add it to HACS as a custom repository](https://hacs.xyz/docs/faq/custom_repositories) using the following details:

- Repository URL: `https://github.com/pauln/ha-samsung-e-paper`
- Category: `Integration`

## Setup / Configuration

Once everything is set up, the integration can wake the E-Paper device from sleep - but it needs to be awake for the initial configuration in order for this to be possible.

1. Wake the device via the Samsung E-Paper app, or using the power button on the device
2. Add the device to Home Assistant, either via autodiscovery or manually
3. Enter the device's IP address and the 6-digit control PIN

## Usage

The integration provides sensors for the following:

- Battery level
- Configured device orientation

It also provides a single action, `samsung_emdx.upload_image`, which requires two parameters: the `device` to upload an image to, and the `image` to upload to it.  As the E-Paper display's colours can be a bit muted, some advanced options are available to preprocess the image:

- `brightness` [integer, 0-200, default: 100]: Adjusts image brightness to the specified percentage of original
- `contrast` [integer, 0-300, default: 100]: Adjusts contrast to the specified percentage of original
- `saturation` [integer, 0-300, default: 100]: Adjusts colour saturation to the specified percentage of original
- `sharpen` [float, 0-10, default: 0]: Sharpens the image by the given factor (0 is unchanged, higher values sharpen more)
- `rotation` [integer, 0|90|180|270]: Rotates the image by the specified number of degrees
- `fit_mode` [string, stretch|contain|cover|crop, default: contain]: How to fit the image to the display if the dimensions don't match
  - `stretch`: stretches the image to fit, resulting in the image being skewed if its aspect ratio is different from the display's
  - `contain`: fits the image within the display, padding with white as needed
  - `cover`: fits the image within the display, cropping off as little as possible to match the display's aspect ratio
  - `crop`: crops the image to fit within the display, without scaling (if the image is smaller, it will be padded with white)

Note that `rotation` is applied before `fit_mode`, so that the image will always fill the display (if using `stretch` or `cover`).  The device's configured orientation will be used to determine whether to fit the image to portrait or landscape dimensions.
