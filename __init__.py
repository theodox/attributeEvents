import json
from functools import partial
import maya.cmds as cmds
import sys

EVENT_ATTRIB = 'changeEvents'
EVENT_ATTRIB_SHORT = 'ace'

import logging

# set up the root file logger. Don't use this directly, use echo from ul.logger
# anywhere outside of bootstrap
_logger = logging.getLogger('attributeEvents')
_print_stream = logging.StreamHandler(sys.stdout)
_print_stream.setFormatter(logging.Formatter("attributeEvents: %(message)s"))
_print_stream.setLevel(logging.WARNING)
_logger.setLevel(logging.WARNING)
_logger.addHandler(_print_stream)
_logger.propagate = False


def set_log_level(lvl):
    _logger.setLevel(lvl)
    _print_stream.setLevel(lvl)


def verbose():
    set_log_level(1)


def quiet():
    set_log_level(49)


def logger():
    return _logger


class WatchedObject(object):
    class StoredEventAttribute(object):
        """ alloww pythonic get-set of stored event handlers """

        def __init__(self, target):
            self.target = target

        def __get__(self, instance, _):
            result = cmds.getAttr("{0}.{1}".format(instance, self.target)) or []
            return map(AttributeNotifier.from_string, result)

        def __set__(self, instance, value):
            cmds.setAttr("{0}.{1}".format(instance, self.target), len(value), *value, type='stringArray')

    class UUID(object):
        """  pythonic getter for object UUID """

        def __get__(self, instance, _):
            return cmds.ls(str(instance), uuid=True)[0]

    # per-instance descriptons
    change_events = StoredEventAttribute(EVENT_ATTRIB)
    uuid = UUID()

    def __init__(self, object):
        """
        Creates a WatchedObject for node <object>, adding the storage attributes if needed.
        """
        self.target = object
        if EVENT_ATTRIB not in (cmds.listAttr(object, ud=True) or []):
            cmds.addAttr(object, ln=EVENT_ATTRIB, sn=EVENT_ATTRIB_SHORT, dt='stringArray', hidden=True)

    def add_event(self, event_key):
        """
        Stores AttributeNotifier <event_key> on this objects
        """
        existing = self.change_events
        if event_key not in existing:
            self.change_events = existing + [event_key]
        else:
            raise RuntimeError, "object {0} already defines a handler for attribut {1}".format(self, event_key)

    def remove_event(self, event_key):
        """
        Remove the event on this object for key <event_key>.  If this does NOT remove the running scriptJob if any -
        just the stored  AttributeNotifier
        """

        existing = self.change_events
        if event_key in existing:
            existing.remove(event_key)
            self.change_events = existing

    def register_event(self, event):
        """
        Create the scriptJob for AttributeNotifier <event>
        """
        attrib = "{0}.{1}".format(self, event.attribute)

        event_data = dict((k, v) for k, v in event.items() if not k.startswith("_"))

        handler = partial(AttributeChangeHandler.handle,
                          uuid=self.uuid,
                          attribute=event.attribute,
                          handler=event.handler,
                          data=event_data)

        ac_job = cmds.scriptJob(kws=1, ac=(attrib, handler))

        delete_handler = partial(AttributeChangeHandler.reassign,
                                 attrib=event.attribute,
                                 uuid=self.uuid,
                                 job=ac_job)

        rn_job = cmds.scriptJob(kws=1, runOnce=True, nnc=(self, delete_handler))

        _logger.info('listening on %s' % attrib)
        return ac_job, rn_job

    def unregister_event(self, event):
        """
        Look for the scriptJob associated with a node-attribute combination and delete it if found
        """
        event_signature = "{0}.{1}".format(self, event.attribute)
        for item in cmds.scriptJob(lj=True):
            if event_signature in item:
                idx, _ = item.split(":")
                cmds.scriptJob(k=int(idx))
                _logger.warning('deleted scriptjob: %s' % _)
                return

    @classmethod
    def find(cls):
        """
        Return a WatchedObject for every element in thge scene with a change_event field
        """
        available_objects = set(cmds.ls("*.{0}".format(EVENT_ATTRIB), o=True, r=True, l=True))
        return [cls(obj) for obj in available_objects]

    @classmethod
    def reactivate(cls):
        """
        find all the stored AttributeNotifiers in the scene and activates their scriptJobs.
        Typically called on scene open.
        """
        event_targets = cls.find()
        counter = 0
        for t in event_targets:
            for e in t.change_events:
                t.register_event(e)
                counter += 1
        _logger.critical('activated {0} events'.format(counter))

    def __repr__(self):
        return self.target


class AttributeNotifier(dict):
    """
    Represents a single attributeChange job which will be fired by the AttributeChangeHandler registry

    Stored keywords are serialzed and deserialized to a hidden object as JSON strings (so things which won't JSON
    sertialize wont' work as keys or values
    """
    ATTRIB = '_attribute'
    HANDLER = '_handler'

    def __init__(self, attribute, handler, **kwargs):
        super(AttributeNotifier, self).__init__(**kwargs)
        self.attribute = attribute
        self.handler = handler

    def __repr__(self):
        store = dict(**self)
        store[self.ATTRIB] = self.attribute
        store[self.HANDLER] = self.handler
        return json.dumps(store)

    @classmethod
    def from_string(cls, string):
        result = json.loads(string)
        attrib = result.pop(cls.ATTRIB)
        handler = result.pop(cls.HANDLER)
        return cls(attrib, handler, **result)


class AttributeChangeHandler(object):
    """
    A global registry that maps string keys to functions so that de-serialized jobs can call them
    """
    REGISTRY = {}
    STRICT = False

    @classmethod
    def handle(cls, **kwargs):
        """
        Route the event from the sender to the appropriate handler
        """
        handler_id = kwargs.get('handler', None)
        sender = cmds.ls(kwargs['uuid'], uuid=True)[0]
        handler = cls.REGISTRY.get(handler_id)
        if handler:
            handler(sender, **kwargs)
        if cls.STRICT:
            cls.fail(sender, **kwargs)
        else:
            cls.unhandled(sender, **kwargs)

    @classmethod
    def reassign(cls, **kwargs):
        """
        Called when an object name changes and we need to repoint script jobs
        """
        cmds.scriptJob(k=kwargs['job'])
        existing = WatchedObject(cmds.ls(kwargs['uuid'], uuid=True)[0])
        for item in existing.change_events:
            if item.attribute == kwargs['attrib']:
                existing.register_event(item)
                return

    @classmethod
    def unhandled(cls, sender, **kwargs):
        """
        just report and continue if handler can't be found
        """
        _logger.warning('unhandled event raised by %s (%s)' % (sender, str(kwargs)))

    @classmethod
    def fail(cls, sender, **kwargs):
        """
        raise an exception when a handler can't be found
        """
        raise RuntimeError('Failed to find event raised by %s (%s)' % (sender, str(kwargs)))

    @classmethod
    def set_strict(cls, val):
        """
        if this is set to true, missing handlers will raise exceptions.
        """
        cls.STRICT = val


    @classmethod
    def register(cls, key, handler):
        cls.REGISTRY[key] = handler

