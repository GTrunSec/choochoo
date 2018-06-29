
from collections.abc import Sequence

from urwid import emit_signal, connect_signal, Widget, ExitMainLoop

from .focus import Focus, FocusAttr, FocusWrap


# new tab manager design

# tabs can be arranged in groups.  group contents can be wiped and re-added.
# this allows tabs in the "middle" of a travers to be rebuilt.
# tabs are assembled in a TabList and then passed to a TabNode which
# contains the group.  the TabNode has to be a widget itself since it
# needs to re-raise signals for tabbing.  because it is a WidgetWrap we need
# the intermediate TabList to assemble the group contents (since the
# TabNode will often be created later).  groups can be nested (a TabNode
# can appear in a TabList) and will behave correctly.  the top-most TabNode
# must have discover() called to set signals for tab looping and to discover
# focuses.

# the functionality depends on Focus.apply taking a keypress argument which
# is duplicated by TabNodes.  on TabNodes this triggers internal logic.


class Tab(FocusWrap):
    """
    A widget wrapper that is added automatically by TagList.add().  Must
    be added to any node that is both target and source of tabbing.
    Intercepts tab keypresses and raises a signal that causes the focus to
    change.

    Normal use is:
        tabs = TabList()
        ...
        widget = tabs.add(Widget(...))
    """

    def __init__(self, w):
        super().__init__(w)

    signals = ['tab']

    def keypress(self, size, key):
        # todo - pass to super first and only handle tabs that are not handled
        # by the widget?
        if key in ('tab', 'shift tab'):
            emit_signal(self, 'tab', self, key)
        else:
            return super().keypress(size, key)


class TabList(Sequence):
    """
    A list of tabbed widgets (in tabbing order) that will be managed by a TabNode.
    The list allows these to be assembled before the TabNode instance is created.
    May include both widgets and other TabNode instances.
    """

    def __init__(self):
        """
        Create an empty list.
        """
        self.__tabs = []

    def append(self, widget_or_node):
        """
        Add a widget to the list of managed widgets.  The return value should be
        used in the constructed tree of widgets (it contains both a Tab target and
        a FocusAttr).
        """
        # todo - how do we modify FocusAttr?
        is_node = isinstance(widget_or_node, TabNode)
        widget_or_node = widget_or_node if is_node else Tab(FocusAttr(widget_or_node))
        self.__tabs.append(widget_or_node)
        return widget_or_node

    def __getitem__(self, item):
        return self.__tabs[item]

    def __len__(self):
        return len(self.__tabs)


class TabNode(FocusWrap):
    """
    A widget wrapper that encapsulates a (local) root node in the widget tree and
    manages all the tabs below that node.

    In dynamic applications the entire TabList may be replaced using replace_all().
    If only a subset of all nodes need to be replaced, use a nested TabNode (so
    the entire contents of the nested node are replaced).

    Normal use is:
        tabs = TabList()
        widget1 = tabs.add(Widget(...))
        ...
        widgetN = tabs.add(Widget(...))
        root = TabNode(Container([widget1, ... windgetN]), tabs)
        root.discover()
    """

    signals = ['tab']

    def __init__(self, log, widget, tab_list):
        """
        Create a (local) root to the widget tree that manages tabs to the widgets
        below (possibly via nested TabNode instances).
        """
        super().__init__(widget)
        self._log = log
        self.__tabs_and_indices = {}
        self.__focus = {}
        self.__root = None
        self.__top = False
        self.__build_data(tab_list)

    def __build_data(self, tab_list):
        for tab in tab_list:
            n = len(self.__focus)
            self.__tabs_and_indices[tab] = n
            self.__tabs_and_indices[n] = tab
            self.__focus[tab] = None
            connect_signal(tab, 'tab', self.tab)

    def replace_all(self, tab_list):
        """
        Replace all the managed tabs.  Typically used at the local root of a dynamic
        section of the widget tree.
        """
        self.__tabs_and_indices = {}
        self.__focus = {}
        self.__build_data(tab_list)

    def tab(self, tab, key):
        """
        The target for tab signals from managed Tab() instances.

        On receiving a signal:
        * check whether tabbing can be handled locally and, if so, activate
        * check if we are root and, if so, loop around
        * otherwise re-raise to tab to remote neighbours (from nested node)
        """
        delta = 1 if key == 'tab' else -1
        n = self.__tabs_and_indices[tab] + delta
        if 0 <= n < len(self.__focus):
            self.__try_set_focus(n, key)
        elif self.__top:
            self.to(None, key)
        else:
            emit_signal(self, 'tab', self, key)

    def __try_set_focus(self, n, key):
        try:
            self._log.debug('Trying to set focus on %s' % self.__tabs_and_indices[n])
            self.__set_focus(self.__tabs_and_indices[n], key)
        except AttributeError:
            self.discover(self.__root)
            self.__set_focus(self.__tabs_and_indices[n], key)

    def __set_focus(self, tab, key):
        self._log.debug('Using %s' % self.__focus[tab])
        self.__focus[tab].to(self.__root, key)

    def to(self, root, key):
        """
        Replicate the Focus() interface.  This is used internally for sub-nodes.
        Instead of assigning focus using Focus.to(),
        """
        if self.__focus:
            n = 0 if key == 'tab' else len(self.__focus) - 1
            self._log.debug('Re-targetting at %d' % n)
            self.__try_set_focus(n, key)
        else:
            # we have nothing to focus, so re-raise signal for remote neighbours
            self._log.debug('Empty so raise signal')
            emit_signal(self, 'tab', self, key)

    def discover(self, root=None, top=True, path=None):
        """
        Register the root widget here before use (in many cases the root node is
        also this TabNode, so no root argument is needed).

        Does a search of the entire widget tree, recording paths to added widgets
        so that they can be given focus quickly.
        """
        self.__top = top
        if root is None:
            root = self
        self.__root = root
        stack = [(self, path if path else [])]
        while stack:
            node, path = stack.pop()
            try:
                # contents can be list or dict
                try:
                    iterator = node.contents.items()
                except AttributeError:
                    try:
                        # possibly a dict
                        iterator = enumerate(node.contents)
                    except TypeError:
                        # possibly a ListBox
                        iterator = node.contents.body.items()
                for (key, data) in iterator:
                    # data can be widget or tuple containing widget
                    try:
                        iter(data)
                    except TypeError:
                        data = [data]
                    new_path = list(path) + [key]
                    for widget in data:
                        if isinstance(widget, Widget):
                            if widget in self.__focus:
                                if isinstance(widget, TabNode):
                                    self.__focus[widget] = widget
                                    widget.discover(root, top=False, path=new_path)
                                else:
                                    self.__focus[widget] = Focus(new_path, self._log)
                            else:
                                stack.append((widget, new_path))
            except AttributeError as e:
                widget = None
                if hasattr(node, '_wrapped_widget'):
                    self._log.warn('Widget %s (type %s) doesn\'t expose contents' % (node, type(node)))
                elif hasattr(node, 'base_widget'):
                    if node == node.base_widget:
                        self._log.warn('Widget with no focus: %s (type %s)' % (node, type(node)))
                    else:
                        widget = node.base_widget
                if widget:
                    if widget in self.__focus:
                        if isinstance(widget, TabNode):
                            self.__focus[widget] = widget
                            widget.discover(root, top=False, path=path)
                        else:
                            self.__focus[widget] = Focus(path, self._log)
                    else:
                        stack.append((widget, path))
        unfound = []
        for widget in self.__focus:
            if not self.__focus[widget]:
                unfound.append('%s (%s)' % (widget, type(widget._w.base_widget)))
        if unfound:
            raise Exception('Could not find %s' % ', '.join(unfound))


class Root(TabNode):

    def __init__(self, log, widget, tab_list, quit='meta q', save='meta s', abort='meta x', saves=None):
        super().__init__(log, widget, tab_list)
        self.__quit = quit
        self.__save = save
        self.__abort = abort
        self.__save_callbacks = saves if saves else []

    def keypress(self, size, key):
        if key == self.__quit:
            self.save()
            raise ExitMainLoop()
        elif key == self.__abort:
            raise ExitMainLoop()
        elif key == self.__save:
            self.save()
        else:
            return super().keypress(size, key)

    def save(self):
        self._log.debug('Saving %s' % self.__save_callbacks)
        for callback in self.__save_callbacks:
            callback(None)