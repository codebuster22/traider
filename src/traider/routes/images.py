"""Routes for image uploads."""
from fastapi import APIRouter, HTTPException

from traider.models import ImageUploadRequest, ImageUploadResponse
from traider.cloudinary_utils import upload_image as cloudinary_upload


router = APIRouter(prefix="/images", tags=["images"])


@router.post("", response_model=ImageUploadResponse, status_code=201)
def upload_image(request: ImageUploadRequest):
    """
    Upload an image to Cloudinary.

    Returns the uploaded image URLs and public ID.
    """
    try:
        result = cloudinary_upload(
            image_data=request.image_data,
            folder=request.folder,
            filename=request.filename
        )
        return ImageUploadResponse(
            url=result["url"],
            secure_url=result["secure_url"],
            public_id=result["public_id"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image upload failed: {str(e)}")
