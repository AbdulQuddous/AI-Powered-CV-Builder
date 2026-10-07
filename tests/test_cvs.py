from copy import deepcopy
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from cvs.models import CV, CVVersion

class CVTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('owner@example.com','Strong-password-735!')
        self.other = get_user_model().objects.create_user('other@example.com','Strong-password-735!')
        login = self.client.post('/api/auth/login/',{'email':self.user.email,'password':'Strong-password-735!'},format='json')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+login.data['access'])
        self.payload = {'name':'Python Developer CV','target_role':'Python Developer','career_level':'fresher','template_id':'modern','data':{}}
    def create(self):
        response=self.client.post('/api/cvs/',self.payload,format='json')
        self.assertEqual(response.status_code,201,response.data)
        return response.data
    def test_create_defaults_and_retrieve(self):
        cv=self.create()
        self.assertEqual(cv['version'],1)
        self.assertEqual(cv['data']['meta']['career_level'],'fresher')
        self.assertEqual(cv['data']['experience'],[])
        response=self.client.get(f"/api/cvs/{cv['id']}/")
        self.assertEqual(response.data,cv)
        self.assertEqual(CVVersion.objects.count(),1)
    def test_list_is_paginated_and_owner_scoped(self):
        self.create()
        CV.objects.create(owner=self.other,name='Secret',data={})
        response=self.client.get('/api/cvs/')
        self.assertEqual(response.data['count'],1)
        self.assertEqual(len(response.data['results']),1)
    def test_update_history_and_meta_sync(self):
        cv=self.create(); url=f"/api/cvs/{cv['id']}/"
        response=self.client.patch(url,{'name':'Updated','target_role':'Backend','expected_version':1},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['version'],2)
        self.assertEqual(response.data['data']['meta']['target_role'],'Backend')
        history=self.client.get(url+'versions/').data['results']
        self.assertEqual([v['version'] for v in history],[2,1])
        self.assertEqual(history[1]['name'],cv['name'])
        self.assertEqual(history[1]['data']['meta']['target_role'],'Python Developer')
    def test_replacement_data_and_conflicts(self):
        cv=self.create(); url=f"/api/cvs/{cv['id']}/"
        data=deepcopy(cv['data']);data['summary']='Developer';data['meta']['target_role']='Engineer'
        response=self.client.patch(url,{'data':data},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['target_role'],'Engineer')
        response=self.client.patch(url,{'data':data,'target_role':'Conflicting'},format='json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(CV.objects.get().version,2)
    def test_stale_update_and_checkpoint(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/"
        response=self.client.post(url+'versions/',{'expected_version':1},format='json')
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.data['version'],2)
        for method, endpoint, body in [('patch',url,{'name':'stale','expected_version':1}),('post',url+'versions/',{'expected_version':1})]:
            response=getattr(self.client,method)(endpoint,body,format='json')
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.data['error']['code'],'version_conflict')
        self.assertEqual(CVVersion.objects.count(),2)
    def test_duplicate_independent_and_delete_cascades(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/"
        duplicate=self.client.post(url+'duplicate/',{},format='json')
        self.assertEqual(duplicate.status_code,201)
        self.assertNotEqual(duplicate.data['id'],cv['id'])
        self.assertEqual(duplicate.data['version'],1)
        self.assertEqual(duplicate.data['data'],cv['data'])
        self.client.patch(url,{'target_role':'Changed'},format='json')
        self.assertEqual(CV.objects.get(pk=duplicate.data['id']).data['meta']['target_role'],'Python Developer')
        self.assertEqual(self.client.delete(url).status_code,204)
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(CVVersion.objects.filter(cv_id=cv['id']).count(),0)
        self.assertEqual(CV.objects.count(),1)
    def test_all_routes_require_authentication(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/";self.client.credentials()
        for method,path in [('get','/api/cvs/'),('post','/api/cvs/'),('get',url),('patch',url),('delete',url),('post',url+'duplicate/'),('get',url+'versions/'),('post',url+'versions/')]:
            self.assertEqual(getattr(self.client,method)(path,{},format='json').status_code,401,(method,path))
    def test_all_detail_routes_hide_other_owners(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/";self.client.force_authenticate(self.other)
        for method,path in [('get',url),('patch',url),('delete',url),('post',url+'duplicate/'),('get',url+'versions/'),('post',url+'versions/')]:
            self.assertEqual(getattr(self.client,method)(path,{},format='json').status_code,404,(method,path))
        self.assertEqual(CV.objects.count(),1)
    def test_reject_owner_and_server_fields(self):
        for key in ['owner','owner_id','version','id','status']:
            response=self.client.post('/api/cvs/',{**self.payload,key:1},format='json')
            self.assertEqual(response.status_code,400,key)
        self.assertEqual(CV.objects.count(),0)
    def test_invalid_data_never_writes(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/"
        invalid=[{},None,[],{'summary':'incomplete'}]
        extra=deepcopy(cv['data']);extra['unknown']=True;invalid.append(extra)
        version=deepcopy(cv['data']);version['schema_version']='2.0';invalid.append(version)
        exp={'company':'X','job_title':'Dev','location':'','start_date':'2025-01','end_date':'','is_current':True,'highlights':[]}
        too_many=deepcopy(cv['data']);too_many['experience']=[exp]*6;invalid.append(too_many)
        dates=deepcopy(cv['data']);dates['experience']=[{**exp,'is_current':False,'end_date':'2024-01'}];invalid.append(dates)
        for data in invalid:
            response=self.client.patch(url,{'data':data},format='json')
            self.assertEqual(response.status_code,400,response.data)
        self.assertEqual(CV.objects.get().version,1)
        self.assertEqual(CVVersion.objects.count(),1)
    def test_transaction_rolls_back_if_snapshot_fails(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/"
        with patch('cvs.services.snapshot',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.client.patch(url,{'name':'Must roll back'},format='json')
        stored=CV.objects.get();self.assertEqual(stored.version,1);self.assertEqual(stored.name,cv['name'])
    def test_empty_patch_and_put_rejected(self):
        cv=self.create();url=f"/api/cvs/{cv['id']}/"
        self.assertEqual(self.client.patch(url,{},format='json').status_code,400)
        self.assertEqual(self.client.put(url,self.payload,format='json').status_code,405)
