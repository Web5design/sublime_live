"""

REMINDERS:
 - When manipulating a page, if you are wiping it,
   remember to clear your views registered live_regions with erase_regions
 - When using dialogs, remember to reset the LiveView's last_click_time
   so it doesn't think the focusing back on the view after you click ok is another click.

"""

import uuid
import time
import functools
import inspect
import sublime
import sublime_plugin


# Storage for all LiveView instances.
# Used to map Views to thier LiveViews
LIVE_VIEWS = {}


def has_live_view(view):
    """
    Returns bool value to indicate if the view has associated LiveView.
    """
    return view.id() in LIVE_VIEWS


def get_live_view(view, **kwargs):
    """
    Will create an instance of LiveView if one doesn't exist.
    If you do not want this, you can use "has_live_view" to test first.
    """
    if not has_live_view(view):
        LiveView(view=view, **kwargs)
    return LIVE_VIEWS.get(view.id(), view)


def del_live_view(view, revert=True):
    """
    Deletes the LiveView if one exists for this view.
    Does nothing if the view does not have a live view.
    """
    if has_live_view(view):
        live_view = get_live_view(view)
        if revert:
            live_view.revert_settings()
        del LIVE_VIEWS[live_view.id()]
        del live_view


class LiveView:
    """
    Extend the sublime text View class.
    We've added:
    - The ability to track the Live Regions.
    - Processor to handle click events in the Live View
      and invoke the processors of the relevant LiveRegions.
    - The ability to say if the Live View is currently clickable or not.
    - Basic settings applying functionality.
    """
    def __init__(
        self,
        view=None,
        window=None,
        flags=0,
        syntax="",
        name=None,
        process=None,
        pre_process=None,
        post_process=None,
        clear_selection=True
    ):
        if view is None and window is None:
            window = sublime.active_window()
        if view is None:
            view = window.new_file(flags, syntax)
        self.view = view

        if name is not None:
            self.set_name(name)

        # Used to identify double clicks in a LiveView.
        # We ignore clicks within 0.1 seconds of last click
        self.last_click_time = 0
        # Register of all LiveRegions associated with this LiveView
        self.live_regions = {}
        # Flag to turn disable clicking in a LiveView
        self.clickable = True
        # Used to store original view settings when we layer LiveView settings on top.
        # These can be used to reset the view settings when the live view is finished.
        self.org_view_settings = {}

        # By default any caret selection is removed. This includes clicks.
        # This stops items getting highlighted by the caret on click.
        self.clear_selection = clear_selection

        # The click handling method/functions of the LiveView.
        # Optional fallback if we don't find a LiveRegion under a click
        self.process = self.process if process is None else process
        self.pre_process = self.pre_process if pre_process is None else pre_process
        self.post_process = self.post_process if post_process is None else post_process

        LIVE_VIEWS[view.id()] = self

    def live_regions_to_regions(self, method):
        """
        Convert any LiveRegions being passed to a sublime.View method with sublime.Regions
        """
        @functools.wraps(method)
        def inner_live_regions_to_regions(*args, **kwargs):
            args = list(args)
            for i, arg in enumerate(args):
                if isinstance(arg, LiveRegion):
                    args[i] = sublime.Region(arg.a, arg.b, arg.xpos)
                elif isinstance(arg, list) and len([x for x in arg if isinstance(x, LiveRegion)]) == len(arg):
                    for j, live_region in enumerate(arg):
                        arg[j] = sublime.Region(live_region.a, live_region.b, live_region.xpos)
            for n, v in kwargs.items():
                if isinstance(v, LiveRegion):
                    kwargs[n] = sublime.Region(v.a, v.b, v.xpos)
                elif isinstance(v, list) and len([x for x in v if isinstance(x, LiveRegion)]) == len(v):
                    for j, live_region in enumerate(v):
                        v[j] = sublime.Region(live_region.a, live_region.b, live_region.xpos)
            return method(*args, **kwargs)
        return inner_live_regions_to_regions

    def __getattr__(self, name):
        """
        If LiveView doesn't have the attribute,
        see if it's View does and use that instead.
        """
        if self.view is not None and hasattr(self.view, name):
            attribute = getattr(self.view, name)
            if callable(attribute):
                attribute = self.live_regions_to_regions(attribute)
            return attribute
        raise AttributeError('\'LiveView\' object has no attribute \'%s\'' % name)

    def apply_settings(self, settings=None, use_defaults=True, read_only=None, scratch=None):
        """
        Apply preset and supplied settings to the View.
        This also records the original state if you want to revert it later.
        """
        if settings is None:
            settings = {}
        if use_defaults:
            defaults = {
                'rulers': [],
                'highlight_line': False,
                'fade_fold_buttons': True,
                'caret_style': 'solid',
                'line_numbers': False,
                'draw_white_space': 'none',
                'gutter': False,
                'word_wrap': False,
                'indent_guide_options': []
            }
            defaults.update(settings)
            settings = defaults

        if read_only is not None:
            self.org_view_settings['read_only'] = self.is_read_only()
            self.set_read_only(read_only)
        if scratch is not None:
            self.org_view_settings['scratch'] = self.is_scratch()
            self.set_scratch(scratch)
        view_settings = self.settings()
        for name, value in settings.items():
            if not name in self.org_view_settings:
                self.org_view_settings[name] = view_settings.get(name)
            view_settings.set(name, value)

    def revert_settings(self):
        """
        If you have layered a LiveView on top of a View.
        You can use this to reset the View's settings if you called
        "apply_settings" to replace them when you created the LiveView.
        """
        read_only = self.org_view_settings.pop('read_only', None)
        if read_only is not None:
            self.set_read_only(read_only)
        scratch = self.org_view_settings.pop('scratch', None)
        if scratch is not None:
            self.set_scratch(scratch)
        view_settings = self.settings()
        for name, value in self.org_view_settings.items():
            view_settings.set(name, value)

    def add_regions(self, key, regions, scope="", icon="", flags=0):
        """
        The same as sublime.View's add_regions method,
        except we also record any LiveRegions being added
        so we can reference them later
        """
        sublime_regions = []
        for region in regions:
            if isinstance(region, LiveRegion):
                if region._key is not None:
                    self.view.erase_regions(region._key)
                region.key = key
                region._key = '%s--%s--%s' % (key, uuid.uuid4(), region.id())
                region.live_view = self
                self.live_regions.setdefault(key, []).append(region)
                self.view.add_regions(region._key, [region], scope, icon, flags)
            else:
                sublime_regions.append(region)
        if sublime_regions:
            self.view.add_regions(key, sublime_regions, scope, icon, flags)

    def get_regions(self, key):
        """
        The same as sublime.View's get_regions method,
        except we also repace any Regions with
        their appropriate LiveRegion counterparts.
        """
        regions = self.view.get_regions(key)
        for live_region in self.live_regions.get(key, []):
            tmp_regions = self.view.get_regions(live_region._key)
            if tmp_regions:
                live_region.region.a = tmp_regions[0].begin()
                live_region.region.b = tmp_regions[0].end()
                regions.append(live_region)
        return regions

    def erase_regions(self, key):
        """
        The same as sublime.View's erase_regions method,
        except we also remove any registered LiveRegions.
        """
        if key in self.live_regions:
            for live_region in self.live_regions[key]:
                if live_region._key is not None:
                    self.view.erase_regions(live_region._key)
                live_region.key = live_region._key = None
            del self.live_regions[key]
        self.view.erase_regions(key)

    def get_live_region(self, method, *args, **kwargs):
        """
        Helper method to call sublime.View methods
        and convert the returned sublime.Region to a LiveRegion
        NOTE: You can of course call the methods directly
        and create a LiveRegion with the returned sublime.Region
        """
        method = getattr(self, method) if isinstance(method, str) else method
        method_args = inspect.getfullargspec(method)[0]
        method_kwargs = dict([(n, v) for n, v in kwargs.items() if n in method_args])
        LiveRegionClass = kwargs.pop('LiveRegionClass', LiveRegion)
        live_region_kwargs = dict([(n, v) for n, v in kwargs.items() if n not in method_args])
        region = method(*args, **method_kwargs)
        return LiveRegionClass(region.a, region.b, region.xpos, **live_region_kwargs)

    def get_live_regions(self, method, *args, **kwargs):
        """
        Helper method to call sublime.View methods
        and convert the returned list of sublime.Regions to LiveRegions
        NOTE: You can of course call the methods directly
        and create LiveRegions with the returned sublime.Regions
        """
        method = getattr(self, method) if isinstance(method, str) else method
        method_args = inspect.getfullargspec(method)[0]
        method_kwargs = dict([(n, v) for n, v in kwargs.items() if n in method_args])
        LiveRegionClass = kwargs.pop('LiveRegionClass', LiveRegion)
        live_region_kwargs = dict([(n, v) for n, v in kwargs.items() if n not in method_args])
        regions = method(*args, **method_kwargs)
        for i, region in enumerate(regions):
            regions[i] = LiveRegionClass(region.a, region.b, region.xpos, **live_region_kwargs)
        return regions

    def clicked(self):
        """
        Handle a click event in a LiveView.
        Checks if the click point was inside a LiveRegion.
        If it was, we call that LiveRegion's proccessing functionality.
        """
        if self.clickable:
            event_time = time.time()
            regions = self.sel()
            # Is this a double click?
            if len(regions) == 1 and\
                    regions[0].empty() and\
                    event_time - self.last_click_time > 0.1:
                self.last_click_time = event_time
                point = regions[0].begin()
                found = False
                for live_regions in self.live_regions.values():
                    for live_region in live_regions:
                        if live_region._key is None:
                            raise LiveError('Registered LiveRegion with no _key.')
                        regions = self.view.get_regions(live_region._key)
                        if not regions:
                            raise LiveError('Could not find Region for LiveRegion key.')
                        elif len(regions) > 1:
                            raise LiveError('LiveRegion key returned more than one Region.')
                        region = regions[0]
                        if region.contains(point) and not point == region.end():
                            live_region.a = region.begin()
                            live_region.b = region.end()
                            if live_region.clickable:
                                if hasattr(live_region, 'pre_process'):
                                    live_region.pre_process(live_region)
                                if hasattr(live_region, 'process'):
                                    live_region.process(live_region)
                                if hasattr(live_region, 'post_process'):
                                    live_region.post_process(live_region)
                            found = True
                            break
                    if found:
                        break
                else:
                    if hasattr(self, 'pre_process'):
                        self.pre_process(self)
                    if hasattr(self, 'process'):
                        self.process(self)
                    if hasattr(self, 'post_process'):
                        self.post_process(self)
        # Should we make this optional?
        # Good for non editable LiveViews but may not be for others.
        if self.clear_selection:
            self.sel().clear()

    def pre_process(self, live_view):
        pass

    def process(self, live_view):
        pass

    def post_process(self, live_view):
        pass


class LiveRegion:
    """
    LiveRegions are sublime regions that are remembered by a LiveView.
    When a point on a LiveView is clicked it will see if any of it's
    LiveRegions span that point and if there is,
    it will either call the processing functionality of the LiveRegion
    or of it's LiveGroup if it belongs to one.
    We can also dictate if a LiveRegion is currently clickable.
    """
    def __init__(
        self,
        a=None,
        b=None,
        xpos=-1,
        process=None,
        pre_process=None,
        post_process=None,
        clickable=True
    ):
        self.region = None
        if a is not None:
            self.set_region(a, b, xpos)
        # The key the LiveRegion was added under.
        self.key = None
        # The actual unique key we added the LiveRegion under.
        self._key = None
        # The LiveView this LiveRegion was added to
        self.live_view = None
        # Flag to turn disable clicking in a LiveRegion
        self.clickable = clickable

        # The click handling method/functions of the LiveRegion.
        self.process = self.process if process is None else process
        self.pre_process = self.pre_process if pre_process is None else pre_process
        self.post_process = self.post_process if post_process is None else post_process

    def set_region(self, a, b=None, xpos=-1):
        if isinstance(a, sublime.Region):
            self.region = a
        else:
            if isinstance(self.region, sublime.Region):
                self.region.a = a
                self.region.b = b
                self.region.xpos = xpos
            else:
                r = sublime.Region(a, b, xpos)
                self.region = r
        return self.region

    def __str__(self):
        return self.region.__str__()

    def __getattr__(self, name):
        """
        If LiveRegio doesn't have the attribute,
        see if it's Region does and use that instead.
        """
        if self.region is not None and hasattr(self.region, name):
            return getattr(self.region, name)
        raise AttributeError('LiveRegion object has no attribute "%s"' % name)

    @property
    def a(self):
        return self.region.a

    @a.setter
    def a(self, value):
        self.region.a = value

    @property
    def b(self):
        return self.region.b

    @b.setter
    def b(self, value):
        self.region.b = value

    def id(self):
        return '%s-%s' % (self.__class__.__name__, id(self))

    def update(self):
        """
        Reset the LiveRegions a and b values in case the Region has moved in the View.
        """
        if self._key is not None:
            regions = self.live_view.get_regions(self._key)
            if not regions:
                raise LiveError('LiveRegion had a key but no region in view.')
            if len(regions) > 1:
                raise LiveError('LiveRegion had a key that returned more than one region from the view.')
            region = regions[0]
            self.region.a = region.begin()
            self.region.b = region.end()
        return self

    def process(self, live_region):
        print('Clicked Live Region: %s : %d\n"""%s"""' % (
            str(live_region),
            live_region.live_view.sel()[0].begin(),
            live_region.live_view.substr(live_region)
            )
        )

    def pre_process(self, live_region):
        pass

    def post_process(self, live_region):
        pass


class UpdateLiveViewCommand(sublime_plugin.TextCommand):
    """
    Generic Text Command to insert, erase or replace data in a view.
    """
    def run(self, edit, data=None, start=0, end=None):
        was_read_only = self.view.is_read_only()
        if was_read_only:
            self.view.set_read_only(False)

        if end is not None and not start == end:
            if data is not None:
                self.view.replace(edit, sublime.Region(start, end), data)
            else:
                self.view.erase(edit, sublime.Region(start, end))
        elif data is not None:
            self.view.insert(edit, start, data)

        if was_read_only:
            self.view.set_read_only(True)


class LiveEventListener(sublime_plugin.EventListener):
    def on_selection_modified(self, view):
        """
        See if the clicked view is a LiveView.
        If it is, the view will decide what to do.
        """
        if has_live_view(view):
            get_live_view(view).clicked()

    def on_close(self, view):
        del_live_view(view)


class LiveError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)
