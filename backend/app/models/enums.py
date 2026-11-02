import enum


class UserRole(str, enum.Enum):
    CLIENT = "client"
    HAIRDRESSER = "hairdresser"
    ADMIN = "admin"


class ExperienceLevel(str, enum.Enum):
    JUNIOR = "junior"
    SENIOR = "senior"
    EXPERT = "expert"


EXPERIENCE_COEFFICIENTS = {
    ExperienceLevel.JUNIOR: 1.3,
    ExperienceLevel.SENIOR: 1.0,
    ExperienceLevel.EXPERT: 0.85,
}


class MediaKind(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class AppointmentStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    PENDING_QUOTE = "pending_quote"


class ConsentType(str, enum.Enum):
    MARKETING = "marketing"
    TERMS_OF_SERVICE = "terms_of_service"
