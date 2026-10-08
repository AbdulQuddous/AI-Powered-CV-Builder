from jsonschema import (
    Draft202012Validator,
)


CHAT_RESPONSE_SCHEMA = {
    "type": "object",

    "properties": {
        "assistant_message": {
            "type": "string",
            "minLength": 1,
        },

        "intent": {
            "type": "string",
            "enum": [
                "collect_information",
                "clarify_information",
                "update_cv",
                "give_suggestion",
                "complete",
            ],
        },

        "section": {
            "type": "string",
            "enum": [
                "target",
                "personal",
                "summary",
                "skills",
                "education",
                "experience",
                "projects",
                "certifications",
                "achievements",
                "languages",
                "review",
            ],
        },

        # =====================================
        # INTERNAL CONVERSATION STATE
        # =====================================

        "state_updates": {
            "type": "object",

            "properties": {
                "target_role": {
                    "type": [
                        "string",
                        "null",
                    ],
                },

                "career_level": {
                    "type": [
                        "string",
                        "null",
                    ],
                    "enum": [
                        "fresher",
                        "experienced",
                        "student",
                        "other",
                        None,
                    ],
                },

                "skipped_personal_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "linkedin",
                            "github",
                            "portfolio",
                        ],
                    },
                },
            },

            "required": [
                "target_role",
                "career_level",
                "skipped_personal_fields",
            ],

            "additionalProperties": False,
        },

        # =====================================
        # PROPOSED CV UPDATES
        # =====================================

        "cv_updates": {
            "type": "object",

            "properties": {
                "personal": {
                    "type": [
                        "object",
                        "null",
                    ],

                    "properties": {
                        "full_name": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },

                        "email": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },

                        "phone": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },

                        "location": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },

                        "linkedin": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },

                        "github": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },

                        "portfolio": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },
                    },

                    "required": [
                        "full_name",
                        "email",
                        "phone",
                        "location",
                        "linkedin",
                        "github",
                        "portfolio",
                    ],

                    "additionalProperties": False,
                },

                "summary": {
                    "type": [
                        "string",
                        "null",
                    ],
                },

                "skills": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "string",
                    },
                },

                "education": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "object",

                        "properties": {
                            "degree": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "institution": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "field_of_study": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "start_date": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "end_date": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "grade": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                        },

                        "required": [
                            "degree",
                            "institution",
                            "field_of_study",
                            "start_date",
                            "end_date",
                            "grade",
                        ],

                        "additionalProperties": False,
                    },
                },

                "experience": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "object",

                        "properties": {
                            "company": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "role": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "location": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "start_date": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "end_date": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "responsibilities": {
                                "type": [
                                    "array",
                                    "null",
                                ],

                                "items": {
                                    "type": "string",
                                },
                            },
                        },

                        "required": [
                            "company",
                            "role",
                            "location",
                            "start_date",
                            "end_date",
                            "responsibilities",
                        ],

                        "additionalProperties": False,
                    },
                },

                "projects": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "object",

                        "properties": {
                            "name": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "description": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },

                            "technologies": {
                                "type": [
                                    "array",
                                    "null",
                                ],

                                "items": {
                                    "type": "string",
                                },
                            },

                            "url": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                        },

                        "required": [
                            "name",
                            "description",
                            "technologies",
                            "url",
                        ],

                        "additionalProperties": False,
                    },
                },

                "certifications": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "string",
                    },
                },

                "achievements": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "string",
                    },
                },

                "languages": {
                    "type": [
                        "array",
                        "null",
                    ],

                    "items": {
                        "type": "string",
                    },
                },
            },

            "required": [
                "personal",
                "summary",
                "skills",
                "education",
                "experience",
                "projects",
                "certifications",
                "achievements",
                "languages",
            ],

            "additionalProperties": False,
        },

        "next_action": {
            "type": "string",

            "enum": [
                "ask_question",
                "give_suggestion",
                "review",
                "complete",
            ],
        },
    },

    "required": [
        "assistant_message",
        "intent",
        "section",
        "state_updates",
        "cv_updates",
        "next_action",
    ],

    "additionalProperties": False,
}


class InvalidAIResponse(Exception):
    pass


def validate_ai_response(data):
    validator = Draft202012Validator(
        CHAT_RESPONSE_SCHEMA
    )

    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: list(
            error.path
        ),
    )

    if errors:
        messages = [
            error.message
            for error in errors
        ]

        raise InvalidAIResponse(
            "; ".join(messages)
        )

    return data