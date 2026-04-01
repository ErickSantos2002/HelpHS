"""
Base Pydantic model shared by all request schemas.

Applies:
  - str_strip_whitespace: removes leading/trailing spaces from all string fields
  - str_min_length enforced by FastAPI/Pydantic per field
"""

from pydantic import BaseModel, ConfigDict


class AppBaseModel(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=False,
    )
