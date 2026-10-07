from enum import Enum

class CVStatus(str, Enum):
    DRAFT = 'draft'
    READY = 'ready'
    ARCHIVED = 'archived'
