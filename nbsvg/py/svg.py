# encoding: utf-8
"""SVG Display and Widgets."""

from __future__ import absolute_import

import types
import inspect
import weakref
import inspect
import numpy as np
from threading import Lock
from string import Template
from copy import copy

from ipywidgets import widgets
from IPython.display import display

try:
    from traitlets import (Any, Bool, Float, Tuple, Unicode,
        CUnicode, HasTraits, Instance, List, Dict, TraitType,
        Type, TraitError, Container, Union)
except ImportError:
    from IPython.utils.traitlets import (Any, Bool, Float,
        Tuple, Unicode, CUnicode, HasTraits, Instance, List,
        Dict, TraitType, Type, TraitError, Container, Union)

# Global Widget Sync Control

class _sync(object):

    _control = True

    def toggle(self):
        """global control for widget activation"""
        try:
            self._control = not self._control
        except UnboundLocalError:
            raise UnboundLocalError('* import cuts global widget sync control')

    def get(self):
        """global widget sync status"""
        return self._control

global_sync = _sync()

#-----------------------------------------------------------------------------
# Utilities
#-----------------------------------------------------------------------------

def generate_selectors(*trait_names, **trait_values):
    """Generate a CompositeSelector using the given trait names and values.

    Notes
    -----
    Keyword 'metadata' in trait_values will allow a check
    for equivalenve of trait metadata. Default to no check.
    If a Selector instance is given in trait_values, a
    special recursive behavior will be executed. See the
    match method docstring in the Selector class for more
    details.
    """
    metadata = trait_values.get('metadata',None)
    if metadata is None:
        metadata = {}
    del trait_values['metadata']
    selectors = []
    for name in trait_names:
        selectors.append(Selector(name,metadata=metadata))
    for name in trait_values.keys():
        selectors.append(Selector(name,trait_values[name],metadata))
    return selectors

def collect(element, selector):
    """Collect the first child in element that matches the selector

    Parameters
    ----------
    element : Element
        the object whose children will be selected
    select : Selector
        A selector object whose match method will be used to
        determine which children of the element are selected.
    """
    children = element.children
    for child in children:
        if isinstance(child, Group):
            return collect(child, selector)
        elif selector.match(child):
            new_child = child
            if isinstance(element,Group):
                copy_display(element,new_child)
            return new_child

def collect_all(element, selector):
    """Collect all children from element that match the selector

    Parameters
    ----------
    element : Element
        the object whose children will be selected
    select : Selector
        A selector object whose match method will be used to
        determine which children of the element are selected.
    """
    collection = []
    children = element.children
    for child in children:
        if isinstance(child, Group):
            for group_child in collect_all(child, selector):
                collection.append(group_child)
        elif selector.match(child):
            new_child = child
            if isinstance(element,Group):
                copy_display(element,new_child)
            collection.append(new_child)
    return collection

def copy_display(from_element, to_element, *exclude):
    """Copy the display attributes from one element to another

    Parameters
    ----------
    from_element : Element
        take display attribtues from this element
    to_element : Element
        apply display attributes to this element
    *exclude : list
        list of attribute names that will not be applied to to_element"""
    for name in from_element.trait_names(display=True):
        if name not in exclude:
            new_trait = from_element._trait_values[name]
            old_trait = to_element._trait_values[name]
            if (
                new_trait != None
                and old_trait is None
                and new_trait != old_trait
            ):
                setattr(to_element,name,new_trait)


#-----------------------------------------------------------------------------
# Basic classes
#-----------------------------------------------------------------------------


class NoDefaultSpecified (object): pass
NoDefaultSpecified = NoDefaultSpecified()

class Undefined (object): pass
Undefined = Undefined()

class Length(CUnicode):

    def validate(self, obj, value):
        """Converts all length inputs to px, ex, em, and %"""
        if isinstance(value,int):
            return unicode(value)+u"px"
        if isinstance(value,str):
            return unicode(value)
        if isinstance(value,unicode):
            return value
        if value is None and self.allow_none is True:
            return value
        else:
            raise TraitError('invalid value for type: %r' % value)

class DataDict(Dict):

    def instance_init(self, obj):
        if self.name not in obj._trait_values:
            super(DataDict,self).instance_init(obj)

    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        else:
            data = {}
            traits = obj.traits()
            for name in traits.keys():
                if isinstance(traits[name],Data):
                    data[name] = getattr(obj,name)
            return data

    def __set__(self, obj, value):
        new = self._validate(obj,value)
        for name in new.keys():
            setattr(obj,name,new[name])
        value = self.__get__(obj)
        super(DataDict,self).__set__(obj,value)

class Data(TraitType):

    def __init__(self, trait, **metadata):
        self.trait = trait
        self.info_text = trait.info_text
        self.default_value = trait.default_value
        super(Data,self).__init__(**metadata)

    def set_handler(self, handler):
        if callable(handler):
            self.handler = handler
        else:
            raise AttributeError('{0} must be a callable'.format(handler))

    def instance_init(self, obj):
        trait = self.trait
        trait.name = self.name
        trait.this_class = self.this_class
        if hasattr(trait, '_resolve_classes'):
            trait._resolve_classes()

        default = lambda name, old, new: new
        default.__name__ = self.name + '_data_handler'
        obj.on_trait_change(default,self.name)

        data = getattr(obj.__class__, 'data')
        data.instance_init(obj)

        super(Data,self).instance_init(obj)

    def __set__(self, obj, value):
        if callable(value):
            self._replace_handler(self, obj, value)
            value = self.__get__(obj)
        super(Data,self).__set__(obj,value)
        # must be careful not to call __set__ in data
        # or else recursion will occur (see DataDict)

    def _replace_handler(self, obj, handler):
        handler_name = self.name+'_data_handler'
        handler.__name__ = handler_name
        try:
            nlist = obj._trait_notifiers[self.name]
        except KeyError:
            obj._trait_notifiers[self.name] = [handler]
            return
        for i in range(len(nlist)):
            c = nlist[i]
            if c.__name__ is handler_name:
                nlist[i] = handler
                return

    def validate(self, obj, value):
        return self.trait.validate(obj,value)

    def __or__(self, other):
        if isinstance(other, Union):
            return Union([self.trait] + other.trait_types)
        else:
            return Union([self.trait, other])

class ReferenceIterator(object):

    def __init__(self,references):
        self.refs = references
        self.i = 0
        
    def __iter__(self):
        self.i = 0
        return self
        
    def next(self):
        try:
            r = self.refs[self.i]
        except IndexError:
            raise StopIteration
        if r() is None:
            return self.next()
        self.i += 1
        return r

#-----------------------------------------------------------------------------
# Collections and Selectors
#-----------------------------------------------------------------------------


class Selector(HasTraits):

    _name = Unicode()
    _value = Any()
    metadata = Dict()

    def __init__(self, name, value=Undefined, metadata=None, *args, **kwargs):
        super(Selector,self).__init__(*args,**kwargs)
        if metadata is None:
            metadata = {}
        self._name = name
        self._value = value
        self.metadata = metadata

    def match(self, element):
        """Returns True if element has all the given trait names and values

        Notes
        -----
        If a Selector instance was passed to self._value, that selector's
        match method will be applied to the value of an attribute in
        element whose name is self._name, where the value is expected to
        be a HasTraits object. If the selector returns False, but the
        HasTraits object also has an attribute whose name is _name, the
        above process will be applied to the value of that attribute
        (in other words the selector will be applied to a family tree
        working upwards from one parent to the next).
        """
        if self._name in element.trait_names(**self.metadata):
            trait_instance = element.traits()[self._name]
        else:
            return False
        if self._value is not Undefined:
            if isinstance(self._value,Selector):
                hastraits_object = getattr(element,self._name)
                try:
                    if not self._value.match(hastraits_object):
                        return False
                except AttributeError:
                    return False
            else:
                check_value = trait_instance._validate(element,self._value)
                if check_value != trait_instance.__get__(element):
                    return False
        if self.metadata != {}:
            for arg in self.metadata.keys():
                try:
                    value = trait_instance.metadata[arg]
                    if value!=self.metadata[arg]:
                        raise KeyError
                except KeyError:
                    return False
        return True

class SelectionMixin(object):
    
    def __init__(self,*args,**kwargs):
        super(SelectionMixin,self).__init__(*args,**kwargs)

    def select(self, *trait_names, **kwargs):
        """Returns the first element having the given trait names, values, and metadata

        Parameters
        ----------
        trait_names : tuple
            Should contain trait names which will be selected for.
        kwargs : dict
            Should contain trait names and values which will be
            selected for. Other keyword arguments are described
            in the notes below.

        Notes
        -----
        Using the keyword 'metadata' in kwargs will allow a
        check for equivalenve of trait metadata for the chilren of
        self. Checks for attr=True by default. Use metadata=None
        to avoid this check.
        If a Selector instance is passed to a name in kwargs,
        the selector's match method will be applied to the value
        held by that name in self, where the value is expected to
        be a HasTraits object. If the selector returns False, but
        the HasTraits object also has an attribute whose name is the
        same as the one passed in kwargs, the above process
        will be applied to the value of that attribute (in other
        words the selector will be applied to a family tree working
        upwards from one parent to the next).
        """
        metadata = kwargs.get('metadata',Undefined)
        if metadata is Undefined:
            kwargs['metadata'] = {'attr':True}
        selectors = generate_selectors(*trait_names, **kwargs)
        cs = CompositeSelector(selectors,metadata=kwargs['metadata'])
        return collect(self,cs)

    def select_all(self, *trait_names, **kwargs):
        """Returns a Composite object filled with all elements having the given trait names, values, and metadata

        Parameters
        ----------
        trait_names : tuple
            Should contain trait names which will be selected for.
        kwargs : dict
            Should contain trait names and values which will be
            selected for. For more special keyword arguments than
            are liste in Notes, see the self.select for more info.

        Notes
        -----
        Using the keyword 'metadata' in kwargs will allow a
        check for equivalenve of trait metadata for the chilren of
        self. Not checked by default.
        Passing True to the keyword 'validate' or 'strict_validate'
        in kwargs allows for the collection to be initialized
        using a type so that the collection's validation methods
        will be checked when appending children. Using 'validate'
        will initialize a Composite object based on the given class.
        Using 'strict_validate' will initialize a Collection object
        based on the given class. Default action is a composite which
        accepts any class.
        If a Selector instance is passed to a name in kwargs,
        the selector's match method will be applied to the value
        held by that name in self, where the value is expected to
        be a HasTraits object. If the selector returns False, but
        the HasTraits object has an attribute whose name is the
        same as the one passed in kwargs, the above process
        will be applied to the value of that attribute (in other
        words the selector will be applied to a family tree working
        upwards from one parent to the next).
        """
        validate = kwargs.get('validate',False)
        kwargs['metadata'] = kwargs.get('metadata',None)
        strict_validate = kwargs.get('strict_validate',False)
        if validate is not False and strict_validate is not False:
            raise ValueError("Must have have keyword arguments for either"
                            " 'valdiate' or 'strict_validate': both were given.")
        if validate:
            del kwargs['validate']
            selectors = generate_selectors(*trait_names, **kwargs)
            cs = CompositeSelector(selectors,metadata=kwargs['metadata'])
            return Composite(collect_all(self,cs),validate)
        elif strict_validate:
            del kwargs['strict_validate']
            selectors = generate_selectors(*trait_names, **kwargs)
            cs = CompositeSelector(selectors,metadata=kwargs['metadata'])
            return Collection(collect_all(self,cs),strict_validate)
        else:
            selectors = generate_selectors(*trait_names, **kwargs)
            cs = CompositeSelector(selectors,metadata=kwargs['metadata'])
            return Collection(collect_all(self,cs))

class Registry(HasTraits):

    klass = Type(allow_none=True)

    def __init__(self, items, type, *args, **kwargs):
        super(Registry,self).__init__(*args, **kwargs)
        self._children = []
        self.klass = type
        self.extend(items)

    @property
    def children(self):
        return [c for c in ReferenceIterator(self._children)]

    @children.setter
    def children(self, value):
        if self.verify(*value):
            self._children = value
        else:
            self.error()

    def append(self, item):
        """Append an item to children."""
        if self.verify(item):
            ref = weakref.ref(item)
            self._children.append(ref)
        else:
            self.error()

    def verify(self, *items):
        """Checks that items contains the appropriate types and returns a boolean."""
        for itm in items:
            if type(itm) is not self.klass and self.klass is not None:
                return False
        else:
            return True

    def extend(self, items):
        """Add the elements of items to self.children"""
        if self.verify(*items):
            self._children.extend([weakref.ref(i) for i in items])

    def error(self):
        e = ('The elements of self.children must'
             ' be instances of {0}'.format(self.klass))
        raise TypeError(e)

class MixedRegistry(Registry):

    def __init__(self, items, type=None, *args, **kwargs):
        super(MixedRegistry,self).__init__(items, type, *args, **kwargs)

    def verify(self, *items):
        """Checks that items contains the appropriate types and returns a boolean."""
        for itm in items:
            if self.klass is not None and not isinstance(itm, self.klass):
                return False
        else:
            return True

    def error(self):
        e = 'The elements of self.children must be subclasses of {0}'.format(self.klass)
        raise TypeError(e)

class MutableRegistryMixin(HasTraits):

    data = DataDict()

    def __init__(self, items, type=None, *args, **kwargs):
        super(MutableRegistryMixin,self).__init__(items, type, *args, **kwargs)

    def __setattr__(self, name, value):
        super(MutableRegistryMixin,self).__setattr__(name,value)
        if hasattr(self,'children'):
            self.has_traits(name,True)
            for ref in self.children:
                setattr(ref(),name,value)

    def declare(self, **trait_values):
        for name in trait_values.keys():
            value = trait_values[name]
            setattr(self,name,value)

    def has_traits(self, trait_name, error=False):
        """Check if the given name is a trait of the elements in self.children

        Notes
        -----
        for `error` equals True, raise a TraitError if a trait name is not
        found in the elements of self.children. Default value is False."""
        for ref in self.children:
            if trait_name not in ref().trait_names():
                if error:
                    raise TraitError('{0} is not an attribute of {1}'.format(trait_name,ref()))
                else:
                    return False
        if not error:
            return True
    
    def _children_changed(self, name, value):
        if not self.verify(*value):
            self.error()

    def append(self, item):
        """Append an item to self.children."""
        if self.verify(item):
            ref = weakref.ref(item)
            self._children.append(ref)
        else:
            self.error()

class ImmutableRegistryMixin(HasTraits):

    metadata = Dict()

    def __init__(self, items, type=None, metadata=None, *args, **kwargs):
        if metadata is not None:
            self.metadata = metadata
        super(ImmutableRegistryMixin,self).__init__(items, type, *args, **kwargs)

class Collection(MutableRegistryMixin, SelectionMixin, Registry):
    pass

class Composite(MutableRegistryMixin, SelectionMixin, MixedRegistry):
    pass

class CompositeSelector(ImmutableRegistryMixin, MixedRegistry):

    def match(self, element):
        """Returns True if element has all the names and values of the selectors in self.children"""
        for ref in self.children:
            if not ref().match(element):
                return False
        else:
            return True

    def append(self, item):
        """Add a selector to self.children."""
        if self.verify(item):
            ref = weakref.ref(item)
            ref().metadata = self.metadata
            self._children.append(ref)
        else:
            self.error()


#-----------------------------------------------------------------------------
# Objects Inhereting From HasTraits
#-----------------------------------------------------------------------------

class BaseElement(HasTraits):

    data = DataDict()
    klass = Type()
    tag = Unicode()
    template = Unicode()
    parent = Instance('%s.BaseElement' % __name__, allow_none=True)
    # traits with `linked=False` are not associated with
    # the self.data dictionary through a change handler
    # even though they have metadata for `attr`
    label = Unicode(attr='id', linked=False) # acts like html id
    kind = Unicode(attr='class', linked=False) # acts like html class
    templ_form = Template('')
    
    def __init__(self,*args,**kwargs):
        super(BaseElement,self).__init__(*args,**kwargs)
        self.on_trait_change(self.update_template,self.trait_names(attr=True))
        self.klass = type(self)

    def declare(self, **new_traits):
        """Reassigns new trait values to self

        Parameters
        ----------
        **new_traits : dict
            dictionary of trait names with their corrisponding trait values.
            new_traits is directly applied to self.trait_values
        """
        for name in new_traits.keys():
            setattr(self, name, new_traits[name])

    def update_template(self):
        """Reevaluate template with self._template_default"""
        self.template = self._template_default()
    
    def _template_default(self):
        """Generate attributes and placeholders for replacement in self._render_template.

        Notes
        -----
        templ_form should be a Template type object where $tag and $attrs will
        be safe_substituted with self.tag and the joined list of formatted
        attributes and placeholders gathered from self.trait_names(attr=True)
        respectively.
        Traits which pass `attr=<string>` to **metadata will still gather
        placeholders from self.trait_names(), however the attribute name for
        that placeholder will be set as the string passed to attr.
        """
        attr_temps = []
        anyattr = lambda v: False if v is None else True
        traits = self.traits(attr=anyattr)
        for name in traits.keys():
            if self._trait_values[name] is not None:
                trait_metadata = getattr(traits[name], 'metadata')
                if isinstance(trait_metadata['attr'],str):
                    attr_temps.append('{0}="{{{1}}}"'.format(trait_metadata['attr'],name))
                elif trait_metadata.get('raw',False):
                    attr_temps.append('{0}={{{0}}}'.format(name))
                else:
                    attr_temps.append('{0}="{{{0}}}"'.format(name))
        return self.templ_form.safe_substitute(tag=self.tag, attrs=' '.join(attr_temps))

    def handle_value(self,name):
        """Given a trait name return a value or formated string.
        
        Notes
        -----
        The output from self.handle_value directly substitutes place holders
        generated in self._template_default when rendering the final template.
        """
        return getattr(self,name)

    def handle_name(self,name):
        """Given a trait name return a formated string.

        Notes
        -----
        The output from self.handle_value should be the name of a place holder.
        This place holder will also be passed into handle_value().
        """
        return name

    def _render_template(self):
        """Replace template placeholders with output from self.handle_value
        
        Notes
        -----
        All names passed to self.handle_value are taken from self.trait_names(),
        and all underscores (`_`) in self.trait_names() will be replaced with
        dashes (`-`) for formatting purposes.
        """
        keys = [self.handle_name(name) for name in self.trait_names()]
        vals = [self.handle_value(name) for name in keys]
        data = dict(zip(keys,vals))
        return self.template.format(**data).replace('_','-')

    def _repr_svg_(self):
        return self._render_template()

class Element(SelectionMixin,BaseElement):

    children = List()
    templ_form = Template('<$tag $attrs>\n{children}\n</$tag>')

    def handle_value(self,name):
        """Given a trait name return a value or formated string.
        
        Notes
        -----
        The output from self.handle_value directly substitutes place holders
        generated in self._template_default when rendering the final template.
        """
        if name == 'children':
            return u'\n'.join([c._render_template() for c in self.children])
        else:
            value = getattr(self,name)
            if value is None:
                return ""
            else:
                return value

    def extend(self,children):
        """Extend self.children by children"""
        for c in children:
            self.append(c)

    def append(self,child):
        """Add a child to self.children"""
        self.children.append(child)

    def Circle(self,**kwargs):
        """Add a circle to self.children"""
        c = Circle(parent=self, **kwargs)
        self.append(c)
        return c

    def Ellipse(self,**kwargs):
        """Add an ellipse to self.children"""
        el = Ellipse(parent=self, **kwargs)
        self.append(el)
        return el

    def Line(self,**kwargs):
        """Add a line to self.children"""
        l = Line(parent=self, **kwargs)
        self.append(l)
        return l

    def Polyline(self,**kwargs):
        """Add a polyline to self.children"""
        pl = Polyline(parent=self, **kwargs)
        self.append(pl)
        return pl

    def Polygon(self,**kwargs):
        """Add a polyline to self.children"""
        pg = Polygon(parent=self, **kwargs)
        self.append(pg)
        return pg

    def Text(self,**kwargs):
        """Add a string of text to self.children"""
        t = Text(parent=self,**kwargs)
        self.append(t)
        return t

    def Group(self,**kwargs):
        """Add a group to self.children"""
        g = Group(parent=self, **kwargs)
        self.append(g)
        return g

    def Path(self, **kwargs):
        """Add a path to self.children"""
        p = Path(parent=self, **kwargs)
        self.append(p)
        return p

#-----------------------------------------------------------------------------
# SVG Objects, Styles, and Shapes
#-----------------------------------------------------------------------------

class SVG(Element):

    tag = Unicode('svg')
    width = Data(Length(100), attr=True)
    height = Data(Length(100), attr=True)

    def __init__(self,*args,**kwargs):
        super(SVG,self).__init__(*args,**kwargs)
        local_sync = kwargs.pop('sync',True)
        if global_sync.get() and local_sync:
            self._widget = SVGWidget(self)

    def append(self,child):
        """Add a child to self.children"""
        self.children.append(child)
        self._notify_widget()

    def _notify_trait(self, name, old, new):
        super(BaseElement,self)._notify_trait(name, old, new)
        if hasattr(self,'_widget'):
            self._notify_widget()

    def _notify_widget(self):
        w = self._widget
        if w is not None:
            w.notify()
        else:
            raise AttributeError("no widget synced for '{0}'".format(self))

    def display(self):
        display(self._widget)

class SVGWidget(widgets.DOMWidget):
    _view_module = Unicode('nbextensions/nbsvg/js/SVGView',sync=True)
    _view_name = Unicode('SVGView', sync=True)
    element = Instance(BaseElement)
    svg = Unicode(sync=True)

    def __init__(self, element, *args, **kwargs):
        super(SVGWidget,self).__init__(*args, **kwargs)
        self.element = element
        self.notify()

    def notify(self):
        svg = self.element._repr_svg_()
        self.svg = svg

class DisplayMixin(HasTraits):

    fill = Data(Unicode(), attr=True, display=True)
    stroke = Data(Unicode(), attr=True, display=True)
    stroke_width = Data(Length(), attr=True, display=True)

    transform = Unicode('""', attr=True, raw=True)
    _translate = Tuple(trans=True, display=True)
    _rotate = Tuple(trans=True, display=True)
    _scale = Tuple(trans=True, display=True)
    _skewX = Tuple(trans=True, display=True)
    _skewY = Tuple(trans=True, display=True)
    _matrix = Tuple(trans=True, display=True)

    def __init__(self, *args, **kwargs):
        self.sync = kwargs.pop('sync',True)
        super(DisplayMixin,self).__init__(*args,**kwargs)
        self.on_trait_change(self._render_transform, self.trait_names(trans=True))

    def _notify_trait(self, name, old, new):
        super(DisplayMixin,self)._notify_trait(name, old, new)
        if global_sync.get() and self.sync:
            self._notify_widget()

    def _notify_widget(self):
        self.parent._notify_widget()

    def _render_transform(self):
        full = ''
        rendered = []
        for name in self.trait_names(trans=True):
            args = getattr(self, name)
            if args not in (tuple(),None):
                string = str(args)
                if string[-2] is ',':
                    string = string[:-2]+')'
                rendered.append('"'+name[1:]+string+'"')
        funcs = ' '.join(rendered)
        if funcs is str():
            setattr(self, 'transform', '""')
        else:
            setattr(self, 'transform', funcs)


    def transformation(self, **kwargs):
        rendered = []
        for name in kwargs:
            try:
                c = getattr(self, name)
            except AttributeError:
                klass = self.__class__.__name__
                raise AttributeError("'{0}' object has no transform function"
                                     " named '{1}'".format(klass,name))
            args = kwargs[name]
            if not isinstance(args,tuple):
                raise ValueError("argument for '{0}' in **kwargs"
                                 " must be a tuple".format(name))
            c(*args)

    def translation(self, *args):
        """translate along the x and y axis
        
        Parameters
        ----------
        *args : tuple(x, y=0)
            providing one argument will translate over x and
            assume that y=0. providing two argumenst will
            translate over both x and y."""
        if len(args) in (0,2):
            pass
        elif len(args)==1:
            args = (args[0],0)
        else:
            raise TypeError("translate() takes 1 or 2 arguments"
                            " ({0} give)".format(len(args)))
        setattr(self, '_translate', args)

    def rotate(self, *args):
        """rotate about (0,0) or rotate about a point
        
        Parameters
        ----------
        *args : tuple(deg)
            providing one argument will rotate about (0,0)
            the given number of degrees.
        *args : tuple(deg, x, y)
            providing three argumenst will rotate about (x,y)
            the given number of degrees."""
        if len(args) not in (0,1,3):
            raise TypeError("rotate() takes 1 or 3 arguments"
                            " ({0} give)".format(len(args)))
        setattr(self, '_rotate', args)

    def scale(self, *args):
        """scale along the x or y axis
        
        Parameters
        ----------
        *args : tuple(value)
            providing one argument will scale along both
            the x and y axis based upond the given value
        *args : tuple(x_val, y_val)
            providing two arguments will scale along the
            x and y axis based upon x_val and y_val
            respectively
        """
        if len(args)>2:
            raise TypeError("scale() takes 1 or 2 arguments"
                            " ({0} give)".format(len(args)))
        setattr(self, '_scale', args)

    def skewing(self, *args):
        """skew the given axis by a given amount.
        
        Parameters
        ----------
        *args : tuple('x',deg)
            skews along the x-axis by the given number of degrees
        *args : tuple('y',deg)
            skews along the y-axis by the given number of degrees

        Notes
        -----
        If deg is None then skew funciton is passed an empty tuple.
        """
        if len(args)==1:
            setattr(self, '_skew'+args[0].upper(), tuple())
        elif len(args)==2:
            setattr(self, '_skew'+args[0].upper(), (args[1],))
        else:
            raise TypeError("scale() takes 1 or 2 arguments ({0}"
                            " give)".format(len(args)))

    def matrix(self, *args):
        """specify a translation matrix
        
        Parameters
        ----------
        *args : tuple(a,b,c,d,e,f)
            the above arguments convert to a matrix of the form:
            ((a, c, e)
             (b, d, f)
             (0, 0, 1))
        
        Notes
        -----
        http://tutorials.jenkov.com/svg/svg-transformation.html#matrix
        """
        if len(args)==0:
            pass
        elif len(args)!=6:
            raise TypeError("scale() takes 6 arguments ({0}"
                            " give)".format(len(args)))
        setattr(self, '_matrix', args)

class Group(DisplayMixin,Element):

    tag = Unicode('g')
    templ_form = Template('<$tag $attrs {transform}>\n{children}\n</$tag>')
    
    def __init__(self,*args,**kwargs):
        super(Group,self).__init__(*args,**kwargs)
        self.on_trait_change(self._group_set,self.trait_names(display=True))

    def _group_set(self, name, old, new):
        """Reconstruct the group's default template after a trait change.
        
        Notes
        -----
        When a display trait is changed, all children within the group
        have this trait reset to `None` so as to override any individual
        settings.
        """
        for c in self.children:
            t = c.traits()[name]
            if not t.allow_none:
                t.allow_none = True
                t.set_metadata('allow_none', True)
            setattr(c, name, None)
            c.template = c._template_default()
        setattr(self, name, new)
        self.update_template()

    def append_collection(self, collection):
        """Extend self.children by the elements in colleciton.children"""
        self.extend([ref() for ref in collection.children])

class VoidElement(BaseElement):

    templ_form = Template('<$tag $attrs/>')

class Text(VoidElement, DisplayMixin):

    tag = Unicode('text')
    templ_form = Template('<$tag $attrs>{string}</$tag>')
    string = Data(Unicode(), attr=True)
    x = Data(Length(3), attr=True)
    y = Data(Length(15), attr=True)
    
    def __init__(self,*args,**kwargs):
        super(Text,self).__init__(*args,**kwargs)
        self.fill = 'black'
        self.stroke = 'none'
        self.stroke_width = 0
        
    def handle_value(self,name):
        """Given a trait name return a value or formated string.
        
        Notes
        -----
        The output from self.handle_value directly substitutes place holders
        generated in self._template_default when rendering the final template.
        """
        value = getattr(self,name)
        if value is None:
            return ""
        else:
            return value

class Shape(DisplayMixin,VoidElement):

    templ_form = Template('<$tag $attrs {transform}/>')

    def __init__(self,*args,**kwargs):
        super(Shape,self).__init__(*args,**kwargs)
        self.fill = 'none'
        self.stroke = 'gray'
        self.stroke_width = 1

class Circle(Shape):
    tag = Unicode('circle')
    cx = Data(Length(12), attr=True)
    cy = Data(Length(12), attr=True)
    r = Data(Length(10), attr=True)

class Ellipse(Shape):

    tag = Unicode('ellipse')
    cx = Data(Length(12), attr=True)
    cy = Data(Length(12), attr=True)
    rx = Data(Length(10), attr=True)
    ry = Data(Length(5), attr=True)

class Polyline(Shape):

    tag = Unicode('polyline')
    points = Data(List(None,[(2,2),(12,12)]), attr=True)

    def handle_value(self,name):
        """Given a trait name return a value or formated string.
        
        Notes
        -----
        The output from self.handle_value directly substitutes place holders
        generated in self._template_default when rendering the final template.
        """
        if name=='points':
            return '\n'.join([unicode(p)[1:-1] for p in self.points])
        else:
            return getattr(self,name)

class Polygon(Polyline):

    tag = Unicode('polygon')
    points = Data(List(None,[(2,30),(12,10),(22,30)]), attr=True)

class Line(Shape):

    tag = Unicode('line')
    points = Data(Tuple((Tuple,Tuple)))
    x1 = Data(Length(2), coords=True, attr=True)
    y1 = Data(Length(2), coords=True, attr=True)
    x2 = Data(Length(12), coords=True, attr=True)
    y2 = Data(Length(12), coords=True, attr=True)

    def __init__(self,*args,**kwargs):
        super(Line,self).__init__(*args,**kwargs)
        self.on_trait_change(self._set_points,self.trait_names(coords=True))
        self.on_trait_change(self._set_coords,'points')
        self._set_points()

    def _set_points(self):
        """Adjust the points trait to match x1, y1, x2, and y2 when they've changed."""
        point_list = [[0,0],[0,0]]
        for name in self.trait_names(coords=True):
            i = int(name[1])-1
            if name[0] == 'x':
                j=0
            if name[0] == 'y':
                j=1
            point_list[i][j] = getattr(self,name)
        self._trait_values['points'] = [tuple(t) for t in point_list]
    
    def _set_coords(self,name,old,new):
        """Adjust the traits x1, y1, x2, and y2 to match points when it's changed."""
        point_list = [[0,0],[0,0]]
        for name in self.trait_names(coords=True):
            i = int(name[1])-1
            if name[0] == 'x':
                j=0
            if name[0] == 'y':
                j=1
            self._trait_values[name] = self.points[i][j]
            point_list[i][j] = self._trait_values[name]
        self._trait_values['points'] = [tuple(t) for t in point_list]

class Path(Shape):

    tag = Unicode('path')
    segments = List()
    d = Data(Unicode(), attr=True)

    def __add__(self, other):
        if isinstance(other, Path):
            self.extend(other.segments)
        elif isinstance(other, PathSegment):
            self.append(other)
        else:
            raise TypeError("Addition for '{0}' object must be with "
                            "'PathSegment' or 'Path' objects.".format(self))
        return self

    def _render_path(self):
        segments = self.segments
        paths = [seg._render_path() for seg in segments]
        d = ' '.join(paths)
        setattr(self, 'd', d)

    def append(self, obj):
        self.segments.append(obj)
        self._render_path()

    def insert(self, index, obj):
        self.segments.insert(index,obj)
        self._render_path()

    def extend(self, objects):
        for o in objects:
            self.append(o)

    def pop(self, index):
        obj = self.segments.pop(index)
        self._render_path()
        return obj

    def M(self, coords=tuple(), *args, **kwargs):
        mt = MoveTo(coords, *args, **kwargs)
        self.append(mt)
        return self

    def m(self, coords=tuple(), *args, **kwargs):
        rmt = MoveTo(coords, *args, **kwargs).rel()
        self.append(rmt)
        return self

    def A(self, coords=tuple(), *args, **kwargs):
        ea = EllipticalArc(coords, *args, **kwargs)
        self.append(ea)
        return self

    def a(self, coords=tuple(), *args, **kwargs):
        rea = EllipticalArc(coords, *args, **kwargs).rel()
        self.append(rea)
        return self

    def L(self, points=None, *args, **kwargs):
        l = LineTo(points,*args, **kwargs)
        self.append(l)
        return self

    def l(self, points=None, *args, **kwargs):
        rl = LineTo(points,*args, **kwargs).rel()
        self.append(rl)
        return self

class PathSegment(HasTraits):

    data = DataDict()
    template = Unicode()
    _command = Unicode()
    absolute = Bool(True)
    close = Bool(False)

    def __init__(self, *args, **kwargs):
        cdict = {}
        for k in kwargs.keys():
            if k in self.coord_names():
                cdict[k] = kwargs[k]
                del kwargs[k]

        super(PathSegment,self).__init__(**kwargs)

        if args == tuple():
            for name in cdict:
                setattr(self, name, cdict[name])
        else:
            if cdict == {}:
                coord_names = self.coord_names()
                for i in range(len(args)):
                    setattr(self, coord_names[i], args[i])
            else:
                raise ValueError('initialize failed due to conflict'
                                 ' between *args and **kwargs')

    def __add__(self, other):
        if isinstance(other,Path):
            other.segments.insert(0,self)
            other._render_path()
        else:
            klass = self.__class__.__name__
            raise TypeError("Addition for '{0}' object must"
                            " be with a 'Path' object")

    def _render_path(self):
        command = self._command
        vals = [self._command]+list(self.coords())
        template = ' '.join([str(v) for v in vals])
        if self.close:
            template += 'Z'
        self.template = template
        return template

    def coords(self):
        return tuple(self._trait_values[c] for c in self.coord_names())

    def coord_names(self):
        anycoord = lambda v: False if v is None else True
        order = lambda name: self.traits()[name].metadata['coord']
        names = self.trait_names(coord=anycoord)
        names.sort(key=order)
        return names

    def _absolute_changed(self, name, value):
        setattr(self, name, value)
        command = self._command
        command = command.upper() if self.absolute else command.lower()
        setattr(self, '_command', command)

    def abs(self):
        self.absolute = True
        return self

    def rel(self):
        self.absolute = False
        return self

class MoveTo(PathSegment):

    _command = Unicode('M')
    x = Data(Float(0), coord=0)
    y = Data(Float(0), coord=1)

class EllipticalArc(PathSegment):

    _command = Unicode('A')
    rx = Data(Float(20), coord=0)
    ry = Data(Float(20), coord=1)
    x_rot = Data(Float(0), coord=2)
    arc_flag = Data(Float(0), coord=3)
    sweep_flag = Data(Float(0), coord=4)
    x = Data(Float(0), coord=5)
    y = Data(Float(0), coord=6)

class LineTo(PathSegment):

    _command = Unicode('L')
    _coords = Data(List(None,[10,10]))

    def __init__(self, *args, **kwargs):
        super(PathSegment,self).__init__(**kwargs)
        self.set_coords(*args)

    @property
    def points(self):
        length = len(self._coords)
        if length%2 != 0:
            raise TraitError('self._coords must have an even number'
                            ' of entries (two per coordinate)')
        points = []
        for i in range(length/2):
            c = tuple(self._coords[i*2:(i*2+2)])
            points.append(c)
        return points

    @points.setter
    def points(self, value):
        coords = []
        for p in value:
            if isinstance(p, tuple) and len(p)==2:
                coords.append(p[0])
                coords.append(p[1])
            else:
                raise TraitError("'point' must be composed of"
                                " tuples each of length two")
        self._coords = coords

    def set_coords(self, *coords):
        if False in [isinstance(c,(int,float)) for c in coords]:
            raise TraitError()
        self._coords = list(coords)

    def coords(self):
        """Returns a copy of the raw coordinates data"""
        return self._coords[:]