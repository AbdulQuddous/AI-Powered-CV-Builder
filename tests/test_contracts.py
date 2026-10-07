import json
from pathlib import Path
from copy import deepcopy
from unittest import TestCase
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from shared.enums.career_level import CareerLevel
from shared.enums.template_type import TemplateType
ROOT=Path(__file__).resolve().parent.parent/'shared'
class ContractTests(TestCase):
    def load(self,name):
        return json.loads((ROOT/'schemas'/f'{name}_schema.json').read_text())
    def test_schemas_valid(self):
        for name in ['cv','user','chat','template']:
            Draft202012Validator.check_schema(self.load(name))
    def test_cv_limits_and_unknown_fields(self):
        cv=json.loads((ROOT/'examples/cv_draft.json').read_text())
        validator=Draft202012Validator(self.load('cv'),format_checker=FormatChecker())
        validator.validate(cv)
        entry={'company':'X','job_title':'Developer','location':'','start_date':'2025-01','end_date':'','is_current':True,'highlights':[]}
        cv['experience']=[deepcopy(entry) for _ in range(5)]
        validator.validate(cv)
        cv['experience'].append(entry)
        with self.assertRaises(ValidationError): validator.validate(cv)
        cv['experience']=[]
        cv['personal']['password']='not allowed'
        with self.assertRaises(ValidationError): validator.validate(cv)
    def test_enum_alignment(self):
        cv=self.load('cv')['properties']
        self.assertEqual(set(cv['meta']['properties']['career_level']['enum'])-{''},{v.value for v in CareerLevel})
        self.assertEqual(set(self.load('template')['properties']['template_type']['enum']),{v.value for v in TemplateType})
    def test_identity(self):
        validator=Draft202012Validator(self.load('user'),format_checker=FormatChecker())
        validator.validate({'user_id':1,'email':'person@example.com'})
        with self.assertRaises(ValidationError): validator.validate({'user_id':1,'email':'bad'})
