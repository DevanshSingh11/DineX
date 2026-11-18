from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit
from .allergens import Allergen

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=220)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1200)]
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=200,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    ),
]
Password = Annotated[str, StringConstraints(min_length=12, max_length=160)]
Slug = Annotated[
    str,
    StringConstraints(
        to_lower=True,
        strip_whitespace=True,
        min_length=2,
        max_length=60,
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
    ),
]
Currency = Literal["INR", "USD", "GBP", "EUR", "AUD", "CAD", "AED", "SGD"]
Role = Literal["Owner", "Admin", "Manager", "Kitchen", "Staff"]
Minor = Annotated[int, Field(strict=True, ge=0, le=100_000_000)]
Positive = Annotated[int, Field(strict=True, gt=0)]
ImagePath = Annotated[str, StringConstraints(max_length=1600)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


def check_image(value):
    if (
        not value
        or value.startswith("/media/")
        and value[6:].replace("/", "").isdigit()
    ):
        return value
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("Use an HTTPS image URL or a DineX image.")
    return value


class Profile(Body):
    name: Name
    contact: Short = ""
    address: Short = ""
    city: Short = ""
    region: Short = ""
    country: Short = ""
    description: Description = ""
    cuisine: Short = ""
    hours: Short = ""
    logo: ImagePath = ""
    cover: ImagePath = ""
    currency: Currency = "INR"
    timezone: Short = "Asia/Kolkata"
    prefix: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, to_upper=True, pattern=r"^[A-Z0-9]{1,8}$"
        ),
    ] = "DX"
    tax_bps: Annotated[int, Field(ge=0, le=10000)] = 0
    charge_bps: Annotated[int, Field(ge=0, le=10000)] = 0

    _image = field_validator("logo", "cover")(check_image)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use a valid IANA time zone.") from None
        return value


class Registration(Profile):
    slug: Slug
    owner_name: Name
    owner_email: Email
    password: Password
    table_count: Annotated[int, Field(ge=0, le=100)] = 0


class Credentials(Body):
    email: Email
    password: Annotated[str, StringConstraints(min_length=1, max_length=160)]


class PasswordChange(Body):
    current: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    replacement: Password


class RestaurantLogin(Credentials):
    slug: Slug


class PlatformAccount(Body):
    name: Name
    email: Email
    password: Password


class Toggle(Body):
    active: bool


class PolicyUpdate(Body):
    approval: bool


class RestaurantState(Body):
    status: Literal["active", "suspended", "deactivated", "rejected"]


class PlanInput(Body):
    name: Name
    max_tables: Annotated[int, Field(ge=1, le=1000)] = 100
    max_staff: Annotated[int, Field(ge=1, le=500)] = 50
    analytics: bool = True
    assistant: bool = True
    trial_days: Annotated[int, Field(ge=0, le=365)] = 0


class Assignment(Body):
    plan_id: Positive
    subscription: Literal["unbilled", "trial", "active", "paused"] = "unbilled"


class StaffInput(Body):
    name: Name
    email: Email
    password: Password
    role: Role
    grants: list[Literal["payment", "adjust"]] = Field(
        default_factory=list, max_length=2
    )


class StaffEdit(Toggle):
    role: Role
    grants: list[Literal["payment", "adjust"]] = Field(
        default_factory=list, max_length=2
    )


class CategoryInput(Body):
    name: Name
    active: bool = True


class OptionInput(Body):
    name: Name
    price: Minor = 0


class GroupInput(Body):
    name: Name
    minimum: Annotated[int, Field(ge=0, le=30)] = 0
    maximum: Annotated[int, Field(ge=1, le=30)] = 1
    options: list[OptionInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def bounds(self):
        names = {option.name.casefold() for option in self.options}
        if (
            self.minimum > self.maximum
            or self.maximum > len(self.options)
            or len(names) != len(self.options)
        ):
            raise ValueError("Check group limits and use distinct option names.")
        return self


class ItemInput(Body):
    category_id: Positive
    name: Name
    description: Description = ""
    price: Minor
    ingredients: Description = ""
    allergens: list[Allergen] = Field(default_factory=list, max_length=24)
    may_contain: list[Allergen] = Field(default_factory=list, max_length=24)
    recipe_status: Literal["unreviewed", "reviewed", "sample"] = "unreviewed"
    dietary: Literal["vegetarian", "vegan", "non-vegetarian", "unspecified"] = (
        "unspecified"
    )
    minutes: Annotated[int, Field(ge=0, le=600)] = 0
    image: ImagePath = ""
    available: bool = True
    featured: bool = False
    archived: bool = False
    groups: list[GroupInput] = Field(default_factory=list, max_length=12)
    _image = field_validator("image")(check_image)

    @model_validator(mode="after")
    def check_recipe(self):
        if self.recipe_status != "unreviewed" and not self.ingredients:
            raise ValueError("List the recipe ingredients before marking it checked.")
        return self


class TableInput(CategoryInput):
    archived: bool = False


class QRAction(Body):
    action: Literal["rotate", "revoke"]


class Enter(Body):
    table_id: Positive
    credential: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class LineInput(Body):
    item_id: Positive
    quantity: Annotated[int, Field(strict=True, ge=1, le=50)]
    options: list[Positive] = Field(default_factory=list, max_length=100)
    note: Short = ""


class OrderInput(Body):
    request_key: Annotated[
        str,
        StringConstraints(min_length=16, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$"),
    ]
    lines: list[LineInput] = Field(min_length=1, max_length=50)


class OrderStep(Body):
    status: Literal["accepted", "preparing", "ready", "served", "cancelled"]
    reason: Short = ""


class BillStep(Body):
    status: Literal[
        "accepted", "prepared", "awaiting_payment", "paid", "completed", "cancelled"
    ]
    adjustment: Minor = 0
    discount: Minor = 0
    reason: Short = ""
    method: Literal["cash", "upi", "card"] | None = None
    reference: Short = ""
    confirmed: bool = False


class ServiceInput(Body):
    kind: Literal[
        "waiter", "water", "cutlery", "assistance", "issue", "ingredient_check"
    ]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=800)] = ""

    @model_validator(mode="after")
    def check_note(self):
        if self.kind == "ingredient_check" and not self.note:
            raise ValueError("Tell staff which ingredients they should check.")
        if self.kind != "ingredient_check" and len(self.note) > 220:
            raise ValueError("Keep the service note within 220 characters.")
        return self


class ServiceStep(Body):
    status: Literal["accepted", "resolved"]


class Question(Body):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
    ]
    avoid: list[Allergen] = Field(default_factory=list, max_length=24)
    confirmed: bool = False
