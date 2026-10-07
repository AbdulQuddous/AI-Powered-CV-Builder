from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

class AuthTests(APITestCase):
    def setUp(self):
        self.payload = {'email':'person@example.com','password':'Different-Strong-728!','full_name':'Person'}
    def register(self):
        return self.client.post('/api/auth/register/',self.payload,format='json')
    def login(self):
        return self.client.post('/api/auth/login/',{'email':'PERSON@example.com','password':self.payload['password']},format='json')
    def test_registration_hash_and_duplicate(self):
        response = self.register()
        self.assertEqual(response.status_code,201)
        self.assertNotIn('password',response.data)
        user = get_user_model().objects.get()
        self.assertTrue(user.check_password(self.payload['password']))
        self.assertNotEqual(user.password,self.payload['password'])
        self.payload['email'] = 'PERSON@example.com'
        self.assertEqual(self.register().status_code,400)
    def test_weak_password(self):
        self.payload['password']='123'
        self.assertEqual(self.register().status_code,400)
        self.assertFalse(get_user_model().objects.exists())
    def test_no_privilege_injection(self):
        self.payload['is_staff']=True
        self.assertEqual(self.register().status_code,400)
    def test_me_and_profile_restrictions(self):
        self.assertEqual(self.client.get('/api/auth/me/').status_code,401)
        self.register()
        tokens=self.login().data
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+tokens['access'])
        self.assertEqual(self.client.get('/api/auth/me/').data['email'],'person@example.com')
        self.assertEqual(self.client.patch('/api/auth/me/',{'full_name':'Updated'},format='json').status_code,200)
        for field in ['email','user_id','is_superuser','password']:
            self.assertEqual(self.client.patch('/api/auth/me/',{field:'bad'},format='json').status_code,400)
    def test_refresh_rotation_and_logout(self):
        self.register()
        tokens=self.login().data
        rotated=self.client.post('/api/auth/refresh/',{'refresh':tokens['refresh']},format='json')
        self.assertEqual(rotated.status_code,200)
        self.assertEqual(self.client.post('/api/auth/refresh/',{'refresh':tokens['refresh']},format='json').status_code,401)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+rotated.data['access'])
        self.assertEqual(self.client.post('/api/auth/logout/',{'refresh':rotated.data['refresh']},format='json').status_code,204)
        self.assertEqual(self.client.post('/api/auth/refresh/',{'refresh':rotated.data['refresh']},format='json').status_code,401)
    def test_logout_cannot_revoke_other_user(self):
        self.register()
        other=get_user_model().objects.create_user('other@example.com','Strong-other-728!')
        refresh=str(RefreshToken.for_user(other))
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+self.login().data['access'])
        self.assertEqual(self.client.post('/api/auth/logout/',{'refresh':refresh},format='json').status_code,400)
        self.assertEqual(self.client.post('/api/auth/refresh/',{'refresh':refresh},format='json').status_code,200)
    def test_inactive_user_and_bad_credentials(self):
        self.register()
        self.payload['password']='incorrect'
        self.assertEqual(self.login().status_code,401)
        user=get_user_model().objects.get()
        user.is_active=False
        user.save()
        self.payload['password']='Different-Strong-728!'
        self.assertEqual(self.login().status_code,401)
    def test_database_case_insensitive_uniqueness(self):
        self.register()
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.bulk_create([get_user_model()(email='PERSON@example.com')])
