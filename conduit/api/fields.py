from importlib import import_module


class APIField(object):
    pass


def import_class(resource_cls_str):
    # import resource class dynamically
    import_str = resource_cls_str.split('.')
    module_str = '.'.join(import_str[:-1])
    cls_str = import_str[-1]
    module = import_module(module_str)
    resource_cls = getattr(module, cls_str)
    return resource_cls


class ForeignKeyField(APIField):
    dehydrate_conduit = (
        'objs_to_bundles',
        'add_resource_uri',
    )

    save_conduit = (
        'check_allowed_methods',
        'get_object_from_kwargs',
        'hydrate_request_data',
        'initialize_new_object',
        'save_fk_objs',
        'auth_put_detail',
        'auth_post_detail',
        'form_validate',
        'put_detail',
        'post_list',
        'save_m2m_objs',
    )

    def __init__(self, attribute=None, resource_cls=None, embed=False):
        self.related = 'fk'
        self.attribute = attribute
        self.embed = embed
        self.resource_cls = resource_cls

    def setup_resource(self):
        """
        Lazy load importing resource cls
        """
        # If we don't do this, imports will fail when trying
        # to import resources in the same file as the related
        # Field instantiation
        # If we are passed the string rep of a resource
        # class in python dot notation, import it
        if isinstance(self.resource_cls, basestring):
            self.resource_cls = import_class(self.resource_cls)

    def dehydrate(self, request, parent_inst, bundle=None):
        """
        Dehydrates a related object by running methods on a related resource
        """
        self.setup_resource()
        # build our request, args, kwargs to simulate regular request
        args = []
        obj = getattr(bundle['obj'], self.attribute)
        kwargs = {'objs': [obj], 'pub': ['detail', 'get']}
        resource = self.resource_cls()
        resource.Meta.api = parent_inst.Meta.api

        ## Only run dehydrate if we are embedding the resource
        if self.embed:
            for methodname in self.dehydrate_conduit:
                method = resource._get_method(methodname)
                (request, args, kwargs,) = method(resource, request, *args, **kwargs)
            # Grab the dehydrated data and place it on the parent's bundle
            related_bundle = kwargs['bundles'][0]
            bundle['data'][self.attribute] = related_bundle['data']
        ## By default we just include the resource uri
        else:
            resource_uri = resource._get_resource_uri(obj=obj)
            bundle['data'][self.attribute] = resource_uri
        return bundle

    def save_related(self, request, parent_inst, obj, rel_obj_data):
        """
        Save the related object from data provided
        """
        self.setup_resource()
        args = []
        kwargs = {
            'request_data': rel_obj_data,
            'pub': []
        }
        # Add field to kwargs as if we had hit detail url
        pk_field = self.resource_cls.Meta.pk_field
        if pk_field in rel_obj_data:
            kwargs[pk_field] = rel_obj_data[pk_field]

        # Do some introspection to tell if we are updating or
        # creating
        if pk_field in kwargs:
            kwargs['pub'].extend(['put', 'detail'])
        else:
            kwargs['pub'].extend(['post', 'list'])

        resource = self.resource_cls()
        resource.Meta.api = parent_inst.Meta.api
        for methodname in self.save_conduit:
            method = resource._get_method(methodname)
            (request, args, kwargs,) = method(resource, request, *args, **kwargs)
        # Grab the dehydrated data and place it on the parent's bundle
        related_obj = kwargs['objs'][0]
        # Now we have to update the FK reference on the original object
        # before saving
        setattr(obj, self.attribute, related_obj)

        return related_obj


class ManyToManyField(APIField):
    dehydrate_conduit = (
        'objs_to_bundles',
        'add_resource_uri',
    )

    save_conduit = (
        'check_allowed_methods',
        'get_object_from_kwargs',
        'hydrate_request_data',
        'initialize_new_object',
        'save_fk_objs',
        'auth_put_detail',
        'auth_post_detail',
        'form_validate',
        'put_detail',
        'post_list',
        'save_m2m_objs',
    )

    def __init__(self, attribute=None, resource_cls=None, embed=False):
        self.related = 'm2m'
        self.attribute = attribute
        self.embed = embed
        self.resource_cls = resource_cls

    def setup_resource(self):
        """
        Lazy load importing resource cls
        """
        # If we don't do this, imports will fail when trying
        # to import resources in the same file as the related
        # Field instantiation
        # If we are passed the string rep of a resource
        # class in python dot notation, import it
        if isinstance(self.resource_cls, basestring):
            self.resource_cls = import_class(self.resource_cls)

    def dehydrate(self, request, parent_inst, bundle=None):
        """
        Dehydrates a related object by running methods on a related resource
        """
        self.setup_resource()
        # build our request, args, kwargs to simulate regular request
        args = []
        objs = getattr(bundle['obj'], self.attribute).all()
        kwargs = {'objs': objs, 'pub': ['list', 'get']}
        resource = self.resource_cls()
        resource.Meta.api = parent_inst.Meta.api

        if self.embed:
            for methodname in self.dehydrate_conduit:
                method = resource._get_method(methodname)
                (request, args, kwargs,) = method(resource, request, *args, **kwargs)

            dehydrated_data = []
            for related_bundle in kwargs['bundles']:
                dehydrated_data.append(related_bundle['data'])
        else:
            dehydrated_data = []
            for obj in objs:
                resource_uri = resource._get_resource_uri(obj=obj)
                dehydrated_data.append(resource_uri)
        bundle['data'][self.attribute] = dehydrated_data
        return bundle

    def save_related(self, request, parent_inst, obj, rel_obj_data):
        """
        Save the related object from data provided
        """
        self.setup_resource()
        # For ManyToMany, rel_obj_data should be formatted
        # as list!
        related_objs = []
        for obj_data in rel_obj_data:
            args = []
            kwargs = {
                'request_data': obj_data,
                'pub': []
            }
            # Add field to kwargs as if we had hit detail url
            pk_field = self.resource_cls.Meta.pk_field
            if pk_field in obj_data:
                kwargs[pk_field] = obj_data[pk_field]

            # Do some introspection to tell if we are updating or
            # creating the current related object
            if pk_field in kwargs:
                kwargs['pub'].extend(['put', 'detail'])
            else:
                kwargs['pub'].extend(['post', 'list'])

            resource = self.resource_cls()
            resource.Meta.api = parent_inst.Meta.api
            for methodname in self.save_conduit:
                method = resource._get_method(methodname)
                (request, args, kwargs,) = method(resource, request, *args, **kwargs)
            # Grab the dehydrated data and place it on the parent's bundle
            related_objs.append(kwargs['objs'][0])

        # Now we remove any ManyToMany relationships if
        # the related obj was not specified in rel_obj_data
        # This is because the rel_obj_data represents the
        # entire value of that field.
        related_manager = getattr(obj, self.attribute)
        for attached_obj in related_manager.all():
            if attached_obj not in related_objs:
                related_manager.remove(attached_obj)

        # Now add any related objects that we created
        # Adding an existing relationship has no effect
        for related_obj in related_objs:
            related_manager.add(related_obj)

        return related_objs
