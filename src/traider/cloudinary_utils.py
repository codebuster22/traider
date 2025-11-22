"""Cloudinary integration for image uploads."""
import os
import base64
from typing import Optional
import cloudinary
import cloudinary.uploader

# Configure Cloudinary from environment variables
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)


def upload_image(
    image_data: str,
    folder: str = "traider",
    resource_type: str = "image",
    filename: Optional[str] = None
) -> dict:
    """
    Upload base64 image to Cloudinary.

    Args:
        image_data: Base64 encoded image string (with or without data URI prefix)
        folder: Cloudinary folder path (default: "traider")
        resource_type: Type of resource (default: "image")
        filename: Optional filename (without extension)

    Returns:
        dict with:
            - url: Public URL of uploaded image
            - secure_url: HTTPS URL of uploaded image
            - thumbnail_url: URL of auto-generated thumbnail
            - public_id: Cloudinary public ID
            - format: Image format (jpg, png, etc.)
            - width: Image width
            - height: Image height
            - bytes: File size in bytes

    Raises:
        Exception: If upload fails or Cloudinary not configured
    """
    # Check if Cloudinary is configured
    if not all([
        os.environ.get("CLOUDINARY_CLOUD_NAME"),
        os.environ.get("CLOUDINARY_API_KEY"),
        os.environ.get("CLOUDINARY_API_SECRET")
    ]):
        raise Exception(
            "Cloudinary not configured. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET environment variables."
        )

    # Handle data URI prefix (e.g., "data:image/png;base64,...")
    if image_data.startswith("data:"):
        # Extract base64 part after comma
        image_data = image_data.split(",", 1)[1]

    # Decode base64
    try:
        image_bytes = base64.b64decode(image_data)
    except Exception as e:
        raise Exception(f"Invalid base64 image data: {str(e)}")

    # Prepare upload options
    upload_options = {
        "folder": folder,
        "resource_type": resource_type,
        "overwrite": False,
        "unique_filename": True,
        # Generate thumbnails automatically
        "eager": [
            {"width": 300, "height": 300, "crop": "fill"},  # Square thumbnail
            {"width": 800, "crop": "limit"}  # Max width preview
        ],
        "eager_async": False,  # Wait for transformations
    }

    # Add filename if provided
    if filename:
        upload_options["public_id"] = f"{folder}/{filename}"
        upload_options["unique_filename"] = False

    # Upload to Cloudinary
    try:
        result = cloudinary.uploader.upload(
            f"data:image/auto;base64,{base64.b64encode(image_bytes).decode()}",
            **upload_options
        )
    except Exception as e:
        raise Exception(f"Cloudinary upload failed: {str(e)}")

    # Extract thumbnail URL (first eager transformation)
    thumbnail_url = None
    if result.get("eager") and len(result["eager"]) > 0:
        thumbnail_url = result["eager"][0].get("secure_url")

    return {
        "url": result["url"],
        "secure_url": result["secure_url"],
        "thumbnail_url": thumbnail_url,
        "public_id": result["public_id"],
        "format": result.get("format"),
        "width": result.get("width"),
        "height": result.get("height"),
        "bytes": result.get("bytes"),
    }


def delete_image(public_id: str) -> bool:
    """
    Delete image from Cloudinary.

    Args:
        public_id: Cloudinary public ID of the image

    Returns:
        bool: True if deleted successfully
    """
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception:
        return False
