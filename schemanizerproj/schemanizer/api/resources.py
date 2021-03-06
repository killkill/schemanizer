import json
import logging
from celery import states
from celery.result import AsyncResult
from django.conf.urls import url
from django.contrib.auth.models import User as AuthUser
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from djcelery import models as djcelery_models
from tastypie.authentication import BasicAuthentication
from tastypie.authorization import Authorization, ReadOnlyAuthorization
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie import fields
import time
from changesetapplies import (
    models as changesetapplies_models,
    tasks as changesetapplies_tasks)
from changesets import changeset_functions
from changesets import models as changesets_models
from changesetreviews import (
    models as changesetreviews_models,
    tasks as changesetreviews_tasks)
from changesettests import models as changesettests_models
from changesetvalidations import models as changesetvalidations_models
from schemaversions import (
    models as schemaversions_models,
    schema_functions)
from servers import models as servers_models
from users import models as users_models
from users import user_functions
from . import authorizations

log = logging.getLogger(__name__)


class AuthUserResource(ModelResource):
    class Meta:
        queryset = AuthUser.objects.all()
        resource_name = 'auth_user'
        fields = ['username', 'first_name', 'last_name', 'last_login']
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']


class RoleResource(ModelResource):
    class Meta:
        queryset = users_models.Role.objects.all()
        resource_name = 'role'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']


class UserResource(ModelResource):
    auth_user = fields.ForeignKey(AuthUserResource, 'auth_user')
    role = fields.ForeignKey(RoleResource, 'role', null=True, blank=True)

    class Meta:
        queryset = users_models.User.objects.all()
        resource_name = 'user'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>%s)/create/$' % (self._meta.resource_name,),
                self.wrap_view('user_create'),
                name='api_user_create',
            ),
            url(
                r'^(?P<resource_name>%s)/update/(?P<user_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('user_update'),
                name='api_user_update',
            ),
            url(
                r'^(?P<resource_name>%s)/delete/(?P<user_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('user_delete'),
                name='api_user_delete',
            ),
        ]

    def user_create(self, request, **kwargs):
        """Creates user.

        request.raw_post_data should be in the following form:
        {
            'name': 'Pilar',
            'email': 'pilar@example.com',
            'role_id': 1,
            'password': 'secret'
        }
        """
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        user = None
        data = {}
        try:
            raw_post_data = json.loads(request.raw_post_data)
            name = raw_post_data['name']
            email = raw_post_data['email']
            role_id = int(raw_post_data['role_id'])
            password = raw_post_data['password']
            user = user_functions.add_user(
                name, email, role_id, password,
                perform_checks=True,
                check_user=request.user.schemanizer_user)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=user, data=data, request=request)
        if user and user.pk:
            bundle = self.full_dehydrate(bundle)

        return self.create_response(request, bundle)

    def user_update(self, request, **kwargs):
        """Updates user.

        request.raw_post_data should be in the following form:
        {
            'name': 'Pilar',
            'email': 'pilar@example.com',
            'role': 1
        }
        """
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        user = None
        data = {}
        try:
            user_id = int(kwargs.get('user_id'))
            raw_post_data = json.loads(request.raw_post_data)
            name = raw_post_data['name']
            email = raw_post_data['email']
            role_id = int(raw_post_data['role_id'])
            user = user_functions.update_user(
                user_id, name, email, role_id,
                perform_checks=True,
                check_user=request.user.schemanizer_user)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=user, data=data, request=request)
        if user and user.pk:
            bundle = self.full_dehydrate(bundle)

        return self.create_response(request, bundle)

    def user_delete(self, request, **kwargs):
        """Deletes user."""
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        user = None
        data = {}
        try:
            user_id = int(kwargs.get('user_id'))
            user = users_models.User.objects.get(pk=user_id)
            user_functions.delete_user(
                user, perform_checks=True,
                check_user=request.user.schemanizer_user)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=user, data=data, request=request)
        if user and user.pk:
            bundle = self.full_dehydrate(bundle)

        return self.create_response(request, bundle)


class EnvironmentResource(ModelResource):
    class Meta:
        queryset = servers_models.Environment.objects.all()
        resource_name = 'environment'
        authentication = BasicAuthentication()
        authorization = authorizations.EnvironmentAuthorization()
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'post', 'put', 'delete', 'patch']


class ServerResource(ModelResource):
    environment = fields.ForeignKey(
        EnvironmentResource, 'environment', null=True, blank=True)

    class Meta:
        queryset = servers_models.Server.objects.all()
        resource_name = 'server'
        authentication = BasicAuthentication()
        authorization = Authorization()
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'post', 'put', 'delete', 'patch']


class DatabaseSchemaResource(ModelResource):
    class Meta:
        queryset = schemaversions_models.DatabaseSchema.objects.all()
        resource_name = 'database_schema'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'id': ALL,
            'name': ALL,
        }


class SchemaVersionResource(ModelResource):
    database_schema = fields.ForeignKey(
        DatabaseSchemaResource, 'database_schema', null=True, blank=True)
    pulled_from = fields.ForeignKey(
        ServerResource, 'pulled_from', null=True, blank=True)

    class Meta:
        queryset = schemaversions_models.SchemaVersion.objects.all()
        resource_name = 'schema_version'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'database_schema': ALL_WITH_RELATIONS
        }

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>%s)/save_schema_dump/$' % (
                    self._meta.resource_name,),
                self.wrap_view('save_schema_dump'),
                name='api_save_schema_dump',
            ),
        ]

    def save_schema_dump(self, request, **kwargs):
        """Creates database schema (if needed) and schema version..

        request.raw_post_data should be in the following form:
        {
            'server_id': 1,
            'database_schema_name': 'test',
        }
        """
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        schema_version = None
        data = {}
        try:
            raw_post_data = json.loads(request.raw_post_data)
            server_id = int(raw_post_data['server_id'])
            database_schema_name = raw_post_data['database_schema_name']

            server = servers_models.Server.objects.get(pk=server_id)

            schema_version = (
                schema_functions.save_schema_dump(
                    server, database_schema_name,
                    perform_checks=True,
                    check_user=request.user.schemanizer_user))
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=schema_version, data=data, request=request)
        if schema_version and schema_version.pk:
            bundle = self.full_dehydrate(bundle)

        return self.create_response(request, bundle)


class ChangesetResource(ModelResource):
    database_schema = fields.ForeignKey(
        DatabaseSchemaResource, 'database_schema', null=True, blank=True)
    reviewed_by = fields.ForeignKey(
        UserResource, 'reviewed_by', null=True, blank=True)
    approved_by = fields.ForeignKey(
        UserResource, 'approved_by', null=True, blank=True)
    submitted_by = fields.ForeignKey(
        UserResource, 'submitted_by', null=True, blank=True)
    before_version = fields.ForeignKey(
        SchemaVersionResource, 'before_version', null=True, blank=True)
    after_version = fields.ForeignKey(
        SchemaVersionResource, 'after_version', null=True, blank=True)
    review_version = fields.ForeignKey(
        SchemaVersionResource, 'review_version', null=True, blank=True)

    class Meta:
        queryset = changesets_models.Changeset.objects.all()
        resource_name = 'changeset'
        authentication = BasicAuthentication()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        authorization = ReadOnlyAuthorization()
        filtering = {
            'id': ALL,
            'review_status': ALL,
        }

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>%s)/submit/$' % (self._meta.resource_name,),
                self.wrap_view('changeset_submit'),
                name='api_changeset_submit',
            ),
            url(
                r'^(?P<resource_name>%s)/update/(?P<changeset_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_update'),
                name='api_changeset_update',
            ),
            url(
                r'^(?P<resource_name>%s)/reject/(?P<changeset_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_reject'),
                name='api_changeset_reject',
            ),
            url(
                r'^(?P<resource_name>%s)/approve/(?P<changeset_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_approve'),
                name='api_changeset_approve',
            ),
            url(
                r'^(?P<resource_name>%s)/soft_delete/(?P<changeset_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_soft_delete'),
                name='api_changeset_soft_delete',
            ),
            url(
                r'^(?P<resource_name>%s)/review/(?P<changeset_id>\d+)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_review'),
                name='api_changeset_review',
            ),
            url(
                r'^(?P<resource_name>%s)/review_status/(?P<task_id>.+?)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_review_status'),
                name='api_changeset_review_status',
            ),
            url(
                r'^(?P<resource_name>%s)/apply/$' % (self._meta.resource_name,),
                self.wrap_view('changeset_apply'),
                name='api_changeset_apply',
            ),
            url(
                r'^(?P<resource_name>%s)/apply_status/(?P<task_id>.+?)/$' % (
                    self._meta.resource_name,),
                self.wrap_view('changeset_apply_status'),
                name='api_changeset_apply_status',
            )
        ]

    def changeset_apply(self, request, **kwargs):
        """Applies changeset.

        request.raw_post_data should be a JSON object in the form:
        {
            "changeset_id": 1,
            "server_id": 1
        }
        """

        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        data = {}
        try:
            post_data = json.loads(request.raw_post_data)
            changeset_id = int(post_data['changeset_id'])
            server_id = int(post_data['server_id'])

            async_result = changesetapplies_tasks.apply_changeset.delay(
                changeset_id, request.user.schemanizer_user.pk, server_id)
            data['task_id'] = async_result.id

        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(data=data, request=request)

        return self.create_response(request, bundle)

    def changeset_apply_status(self, request, **kwargs):
        """Checks review thread status."""

        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)

        data = {}
        try:
            task_id = kwargs['task_id']
            task_states = djcelery_models.TaskState.objects.filter(task_id=task_id)

            messages = []
            changeset_detail_apply_ids = []

            if task_states.exists():
                task_state = task_states[0]
                data['task_active'] = task_state.state in states.UNREADY_STATES
                async_result = AsyncResult(task_state.task_id)
                result = async_result.result

                if result:
                    messages = result.get('messages', [])
                    changeset_detail_apply_ids = result.get(
                        'changeset_detail_apply_ids', [])

            data['messages'] = messages
            data['changeset_detail_apply_ids'] = changeset_detail_apply_ids
            site = Site.objects.get_current()
            apply_results_url = 'http://%s%s?task_id=%s' % (
                site.domain,
                reverse('changesetapplies_changeset_applies'),
                task_id)
            data['apply_results_url'] = apply_results_url

        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(data=data, request=request)

        return self.create_response(request, bundle)

    def changeset_review_status(self, request, **kwargs):
        """Checks review status."""

        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)

        data = {}
        try:
            task_id = kwargs['task_id']
            log.debug('task_id = %s', task_id)

            task_state = None
            max_tries = 3
            tries = 0
            while True:
                tries += 1
                log.debug('tries = %s', tries)
                try:
                    task_state = djcelery_models.TaskState.objects.get(
                        task_id=task_id)
                    break
                except:
                    if tries >= max_tries:
                        log.exception('EXCEPTION')
                        raise
                    else:
                        time.sleep(3)

            data['task_active'] = task_state.state in states.UNREADY_STATES
            ar = AsyncResult(task_id)
            result = ar.result
            if result and isinstance(result, dict) and 'message' in result:
                data['message'] = result['message']

            changeset_review_qs = (
                changesetreviews_models.ChangesetReview.objects.filter(
                    task_id=task_id))
            data['changeset_test_ids'] = []
            data['changeset_validation_ids'] = []
            if changeset_review_qs.exists():
                changeset_review_obj = changeset_review_qs[0]
                changeset = changeset_review_obj.changeset
                log.debug('changeset = %s', changeset)
                changeset_tests = changesettests_models.ChangesetTest.objects.filter(
                    changeset_detail__changeset=changeset)
                changeset_validations = changesetvalidations_models.ChangesetValidation.objects.filter(
                    changeset=changeset)
                if changeset_tests:
                    data['changeset_test_ids'] = [obj.pk for obj in changeset_tests]
                if changeset_validations:
                    data['changeset_validation_ids'] = [obj.pk for obj in changeset_validations]

                site = Site.objects.get_current()
                review_results_url = 'http://%s%s' % (
                    site.domain,
                    reverse(
                        'changesetreviews_result', args=[changeset.id]))
                data['review_results_url'] = review_results_url

        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(data=data, request=request)

        return self.create_response(request, bundle)

    def changeset_review(self, request, **kwargs):
        """Reviews changeset.

        request.raw_post_data should be in the following form:
        {
            "schema_version_id": 1
        }

        Successful call would have the following keys in the return value:
            task_id
                - Changeset review task ID
        """

        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        data = {}
        try:
            changeset_id = int(kwargs.get('changeset_id'))
            post_data = json.loads(request.raw_post_data)
            schema_version_id = int(post_data['schema_version_id'])

            async_result = changesetreviews_tasks.review_changeset.delay(
                changeset_pk=changeset_id,
                schema_version_pk=schema_version_id,
                reviewed_by_user_pk=request.user.schemanizer_user.pk
            )
            data['task_id'] = async_result.id

        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(data=data, request=request)

        return self.create_response(request, bundle)

    def changeset_submit(self, request, **kwargs):
        """Submits changeset.

        request.raw_post_data should be in the following form:
        {
            'changeset': {
                'database_schema_id': 1,
                'type': 'DDL:Table:Create',
                'classification': 'painless',
                'review_version_id': 1,
            },
            'changeset_details': [
                {
                    'type': 'add',
                    'description': 'create a table',
                    'apply_sql': 'create table t1 (id int primary key auto_increment)',
                    'revert_sql': 'drop table t1'
                }
            ]
        }
        """

        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)
        #self.throttle_check(request)

        changeset = None
        data = {}
        try:
            raw_post_data = json.loads(request.raw_post_data)
            allowed_fields = (
                'database_schema_id', 'type', 'classification',
                'review_version_id',)
            changeset_data = raw_post_data['changeset']
            for k, v in changeset_data.iteritems():
                if k not in allowed_fields:
                    raise Exception('Changeset has invalid field \'%s\'.' % (k,))
            if 'database_schema_id' in changeset_data:
                database_schema_id = int(changeset_data.pop('database_schema_id'))
                changeset_data['database_schema'] = (
                    schemaversions_models.DatabaseSchema.objects.get(
                        pk=database_schema_id))
            if 'review_version_id' in changeset_data:
                review_version_id = int(changeset_data.pop('review_version_id'))
                changeset_data['review_version'] = (
                    schemaversions_models.SchemaVersion.objects.get(
                        pk=review_version_id))
            changeset = changesets_models.Changeset(**changeset_data)

            changeset_details_data = raw_post_data['changeset_details']
            changeset_details = []
            for changeset_detail_data in changeset_details_data:
                changeset_detail = changesets_models.ChangesetDetail()
                for k, v in changeset_detail_data.iteritems():
                    setattr(changeset_detail, k, v)
                changeset_details.append(changeset_detail)

            changeset = changeset_functions.submit_changeset(
                from_form=False,
                changeset=changeset,
                changeset_detail_list=changeset_details,
                submitted_by=request.user.schemanizer_user,
                request=request
            )

        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=changeset, data=data, request=request)
        if changeset and changeset.pk:
            bundle = self.full_dehydrate(bundle)

        #self.log_throttled_access(request)
        return self.create_response(request, bundle)

    def changeset_update(self, request, **kwargs):
        """Updates changeset.

        request.raw_post_data should be in the following form:
        {
            'changeset': {
                'database_schema_id': 1,
                'type': 'DDL:Table:Create',
                'classification': 'painless',
                'review_version_id': 1
            },
            'changeset_details': [
                {
                    'id': 1,
                    'type': 'add',
                    'description': 'create a table',
                    'apply_sql': 'create table t1...',
                    'revert_sql': 'drop table t1'
                },
                {
                    'type': 'add',
                    'description': 'create a table',
                    'apply_sql': 'create table t2...',
                    'revert_sql': 'drop table t2'
                }
            ],
            'to_be_deleted_changeset_detail_ids': [3, 4, 5]
        }
        """
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)

        changeset = None
        data = {}
        try:
            changeset_id = int(kwargs.get('changeset_id'))
            changeset = changesets_models.Changeset.objects.get(
                pk=changeset_id)

            post_data = json.loads(request.raw_post_data)
            changeset_data = post_data['changeset']

            allowed_fields = (
                'database_schema_id', 'type', 'classification',
                'review_version_id')
            for k, v in changeset_data.iteritems():
                if k not in allowed_fields:
                    raise Exception('Changeset has invalid field \'%s\'.' % (k,))
                if k == 'database_schema_id':
                    database_schema = (
                        schemaversions_models.DatabaseSchema.objects.get(
                            pk=int(v)))
                    changeset.database_schema = database_schema
                else:
                    setattr(changeset, k, v)

            to_be_deleted_changeset_detail_ids = post_data['to_be_deleted_changeset_detail_ids']
            to_be_deleted_changeset_details = []
            for cdid in to_be_deleted_changeset_detail_ids:
                tbdcd = changesets_models.ChangesetDetail.objects.get(
                    pk=int(cdid))
                to_be_deleted_changeset_details.append(tbdcd)

            changeset_details_data = post_data['changeset_details']
            changeset_details = []
            for cdd in changeset_details_data:
                if 'id' in cdd:
                    changeset_detail = changesets_models.ChangesetDetail.objects.get(
                        pk=int(cdd['id']))
                else:
                    changeset_detail = changesets_models.ChangesetDetail()
                for k, v in cdd.iteritems():
                    if k not in ('id',):
                        setattr(changeset_detail, k, v)
                changeset_details.append(changeset_detail)

            # changeset = changeset_logic.changeset_update(
            #     changeset, changeset_details,
            #     to_be_deleted_changeset_details, request.user.schemanizer_user)
            changeset = changeset_functions.update_changeset(
                from_form=False, changeset=changeset,
                changeset_detail_list=changeset_details,
                to_be_deleted_changeset_detail_list=to_be_deleted_changeset_details,
                updated_by=request.user.schemanizer_user,
                request=request)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=changeset, data=data, request=request)
        if changeset and changeset.pk:
            bundle = self.full_dehydrate(bundle)

        return self.create_response(request, bundle)

    def changeset_reject(self, request, **kwargs):
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)
        #self.throttle_check(request)

        changeset = None
        data = {}
        try:
            changeset = changesets_models.Changeset.objects.get(
                pk=int(kwargs['changeset_id']))
            changeset = changeset_functions.reject_changeset(
                changeset,
                request.user.schemanizer_user)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=changeset, data=data, request=request)
        if changeset and changeset.pk:
            bundle = self.full_dehydrate(bundle)

        #self.log_throttled_access(request)
        return self.create_response(request, bundle)

    def changeset_approve(self, request, **kwargs):
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)
        #self.throttle_check(request)

        changeset = None
        data = {}
        try:
            changeset = changesets_models.Changeset.objects.get(
                pk=int(kwargs['changeset_id']))
            changeset = changeset_functions.approve_changeset(
                changeset,
                request.user.schemanizer_user)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=changeset, data=data, request=request)
        if changeset and changeset.pk:
            bundle = self.full_dehydrate(bundle)

        #self.log_throttled_access(request)
        return self.create_response(request, bundle)

    def changeset_soft_delete(self, request, **kwargs):
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)
        #self.throttle_check(request)

        changeset = None
        data = {}
        try:
            changeset = changesets_models.Changeset.objects.get(
                pk=int(kwargs['changeset_id'])
            )
            changeset = changeset_functions.soft_delete_changeset(
                changeset, request.user.schemanizer_user)
        except Exception, e:
            log.exception('EXCEPTION')
            data['error_message'] = '%s' % (e,)
        bundle = self.build_bundle(obj=changeset, data=data, request=request)
        if changeset and changeset.pk:
            bundle = self.full_dehydrate(bundle)

        #self.log_throttled_access(request)
        return self.create_response(request, bundle)


class ChangesetDetailResource(ModelResource):
    changeset = fields.ForeignKey(
        ChangesetResource, 'changeset', null=True, blank=True)

    class Meta:
        queryset = changesets_models.ChangesetDetail.objects.all()
        resource_name = 'changeset_detail'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'id': ALL,
            'changeset': ALL_WITH_RELATIONS,
        }


class TestTypeResource(ModelResource):
    class Meta:
        queryset = changesettests_models.TestType.objects.all()
        resource_name = 'test_type'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'id': ALL
        }


class ChangesetTestResource(ModelResource):
    changeset_detail = fields.ForeignKey(
        ChangesetDetailResource, 'changeset_detail', null=True, blank=True)
    test_type = fields.ForeignKey(
        TestTypeResource, 'test_type', null=True, blank=True)

    class Meta:
        queryset = changesettests_models.ChangesetTest.objects.all()
        resource_name = 'changeset_test'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'changeset_detail': ALL_WITH_RELATIONS,
            'test_type': ALL_WITH_RELATIONS,
        }


class ValidationTypeResource(ModelResource):
    class Meta:
        queryset = changesetvalidations_models.ValidationType.objects.all()
        resource_name = 'validation_type'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'id': ALL
        }


class ChangesetValidationResource(ModelResource):
    changeset = fields.ForeignKey(
        ChangesetResource, 'changeset', null=True, blank=True)
    validation_type = fields.ForeignKey(
        ValidationTypeResource, 'validation_type', null=True, blank=True)

    class Meta:
        queryset = changesetvalidations_models.ChangesetValidation.objects.all()
        resource_name = 'changeset_validation'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'changeset': ALL_WITH_RELATIONS,
            'validation_type': ALL_WITH_RELATIONS,
        }


class ChangesetDetailApplyResource(ModelResource):
    changeset_detail = fields.ForeignKey(
        ChangesetDetailResource, 'changeset_detail', null=True, blank=True)
    environment = fields.ForeignKey(
        EnvironmentResource, 'environment', null=True, blank=True)
    server = fields.ForeignKey(ServerResource, 'server', null=True, blank=True)

    class Meta:
        queryset = changesetapplies_models.ChangesetDetailApply.objects.all()
        resource_name = 'changeset_detail_apply'
        authentication = BasicAuthentication()
        authorization = ReadOnlyAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        filtering = {
            'changeset_detail': ALL_WITH_RELATIONS,
        }
