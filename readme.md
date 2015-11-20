attributeEvents
===============

A simple module for managing attributeChanged scriptjobs in Maya.


Intro
-----
AttributeChanged scriptJobs in Maya are a handy way of getting notified about user actions or scene changes.  However they usually require cumbersome setup: you have to explicitly 
attach a scriptJob to every object-attribute combination you want to track and you have re-create any scriptJobs when objects are renamed or deleted and when you open a new scene.

This module is intended to simplify that.

Basics:
-------

The module has two main parts. The AttributeChangeHandler class is a central registry for attribute changes.  You register handlers by providing a string name a function.  For example, 
here's a handler which prints a message when fired:


```
    def handle_attribute(sender, **kw):
        print sender, " was changed"

```

to make this handler available to scriptJobs you register it:

```

    AttributeChangeHandler.register('notify', handle_attribute)

```

Note thate the key is a string, but we pass the handler function directly. the Handler could, if needed, be a class or intance method -- it does however need to have the signature 

```
 
    def function (sender, **kw):
        # etc
```

where `sender` is the maya node and **kw is a typical keyword-argument dictionary. You can ignore either of these in the actual handler if you want to -- but the handler has to accept 
them.


This handler will fire if somebody calls `AttributeChangeHandler.handle('notify')` and passes a sender (and optionally, keyword arguments).  To hook it a scriptjob we create a 
`WatchedObject` from a Maya node and tell it we want to fire the notify handler on a particular attribute change:


```
    # this manages storing and retrieving notifications between sessions
    watched = WatchedObject('pCube1')
    
    # this says 'fire the notify event when a translate attribute changes' - it can be reused by multiple objects
    notifier = AttributeNotifier('translate', 'notify')
    
    # store the event on the node for future sessions
    watched.add_event(notifier)

    # activate the scriptJob
    watched.register_event(notifier)

```

Now everytime `pCube1` is moved the notification message will print out.  

All of that could be done with conventional scriptJobs.  However the setup is also stored on the node itself so that it can be re-started in another maya session.  Calling


```
    WatchedObject.reactivate()

```

Will find all objects in the scene which have saved AttributeNotifiers attached and start up the associated script job.  This is not done automatically by default -- activating lots of 
scripts on open is a potential security risk so you want to manage it yourself -- but you can easily attach this call to post-file-open callback to automatically revive any stored 
notifications.
