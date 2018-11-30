
from abc import ABC, abstractmethod
from enum import IntEnum


class MatchType(IntEnum):
    '''
    Control how MBRs are matched.
    '''

    EQUAL = 0  # request exactly equal to node
    CONTAINED = 1  # request contained in node
    CONTAINS = 2  # request contains node
    INTERSECT = 3  # request and node intersect


class BaseTree(ABC):

    # nodes in the tree are (height, data) where
    #   height = 0 for leaf nodes
    #   data is [(mbr, value), (mbr, value), ...] for leaf nodes
    #   data is [(mbr, children), (mbr, children), ...] for internal nodes
    #     where children is [(height, data), (height, data), ...]
    # the empty root is None

    # insertion/retrieval semantics are subtly different to a hash table:
    #   you can ask for matches that are exactly equal, overlap, contain or are contained by the box
    #   you can store multiple values at the same key
    #   you can store the same value multiple times at the same key
    #   both the above mean that querying is an iterator over matches
    # these issues above affect deletion:
    #   you will delete everything you would match
    #   you can specify a value on deletion, which provides an additional constraint
    #   but you could still delete multiple nodes
    #   (even with equality matching, (key, value) isn't guaranteed unique)
    # in other words, if you want unique (key, value) or unique key you must enforce it yourself.

    def __init__(self, max_entries=8, min_entries=None):
        '''
        Create an empty tree.

        `max_entries` is the maximum number of children a node can have.
        This data structure was originally designed for mass storage, where such a parameter is important.
        For in-memory use, it doesn't matter so much, but some quick tests suggest 8 is a reasonable choice.
        '''
        if not min_entries:
            min_entries = max_entries // 2
        if min_entries > max_entries // 2:
            raise Exception('Min number of entries in a node is too high')
        if min_entries < 1:
            raise Exception('Min number of entries in a node is too low')
        self._max = max_entries
        self._min = min_entries
        self._root = None
        self._size = 0

    def get_point(self, x, y, value=None, match=MatchType.EQUAL):
        '''
        An iterator over entries (value, box) of nodes that match the given point.

        If `value` is given only entries with the same value are returned
        (this allows for storing "types of points", for example).
        The `match` describes the kind of matching done.

        Note that points are expanded to (zero-area) boxes internally and returned as such.
        '''
        yield from self._get_normalized_box((x, y, x, y), value, match)

    def get_box(self, x1, y1, x2, y2, value=None, match=MatchType.EQUAL):
        '''
        An iterator over entries (value, MBR) of nodes that match the given box.

        If `value` is given only entries with the same value are returned,
        The `match` describes the kind of matching done.
        '''
        yield from self._get_normalized_box(self._normalize_mbr(x1, y1, x2, y2), value, match)

    def _get_normalized_box(self, mbr, value, match):
        if self._root:
            yield from self._get_node(self._root, mbr, value, match)

    def _get_node(self, node, mbr, value, match):
        height, data = node
        for mbr_node, contents_node in data:
            if height:
                if (match in (MatchType.EQUAL, MatchType.CONTAINED) and self._contains(mbr_node, mbr)) or \
                        (match in (MatchType.CONTAINS, MatchType.INTERSECT) and self._intersect(mbr_node, mbr)):
                    yield from self._get_node(contents_node, mbr, value, match)
            else:
                if value is None or value == contents_node:
                    if (match == MatchType.EQUAL and mbr == mbr_node) or \
                            (match == MatchType.CONTAINED and self._contains(mbr_node, mbr)) or \
                            (match == MatchType.CONTAINS and self._contains(mbr, mbr_node)) or \
                            (match == MatchType.INTERSECT and self._intersect(mbr, mbr_node)):
                        yield contents_node, mbr_node

    def add_point(self, value, x, y):
        '''
        Add value at a single point.
        '''
        self._add_normalized_mbr(0, (x, y, x, y), value)
        self._size += 1  # not in _add_normalized_mbr to avoid counting reinserts

    def add_box(self, value, x1, y1, x2, y2):
        '''
        Add value in a box.
        '''
        self._add_normalized_mbr(0, self._normalize_mbr(x1, y1, x2, y2), value)
        self._size += 1  # not in _add_normalized_mbr to avoid counting reinserts

    def _add_normalized_mbr(self, target, mbr, value):
        '''
        Internal insertion.

        `target` is the height for insertion.  This allows for subtrees to be re-inserted as a whole.
        '''
        if self._root:
            if target > self._root[0]:
                raise Exception('Cannot add node at height %d in tree of height %d' % (target, self._root[0]))
            split = self._add_node(self._root, target, value, mbr)
            if split:
                height = split[0][1][0] + 1
                self._root = (height, split)
        else:
            if target:
                raise Exception('Cannot add node at height %d in empty tree' % target)
            self._root = (0, [(mbr, value)])

    def _add_node(self, node, target, value, mbr):
        '''
        Internal insertion at or below a given node.
        '''
        height, data = node
        if height != target:
            i_best, mbr_best = self._best(data, mbr, height)
            child = data[i_best][1]
            data[i_best] = (mbr_best, child)
            split = self._add_node(child, target, value, mbr)
            if split:
                del data[i_best]
                data.extend(split)
                if len(data) <= self._max:
                    return None
                else:
                    return self._split(height, data)
        else:
            data.append((mbr, value))
            if len(data) <= self._max:
                return None
            else:
                return self._split(height, data)

    def _best(self, data, mbr, height):
        '''
        Given a list of nodes, find the node whose area increases least when the given MBR is added.
        '''
        i_best, mbr_best, area_best, delta_area_best, len_best = None, None, None, None, None
        for i_child, (mbr_child, data) in enumerate(data):
            if i_best is None:
                i_best = i_child
                mbr_best = self._merge(mbr_child, mbr)
                area_best = self._area(mbr_best)
                delta_area_best = self._area(mbr_best) - self._area(mbr_child)
                len_best = len(data)
            else:
                mbr_merge = self._merge(mbr_child, mbr)
                area_merge = self._area(mbr_merge)
                delta_area_merge = area_merge - self._area(mbr_child)
                if delta_area_merge < delta_area_best or \
                        (delta_area_merge == delta_area_best and area_merge < area_best) or \
                        (delta_area_merge == delta_area_best and area_merge == area_best and
                        height and len(data) < len_best):
                    i_best, mbr_best, area_best, delta_area_best, len_best = \
                        i_child, mbr_merge, area_merge, delta_area_merge, len(data)
        return i_best, mbr_best

    def _calculate_mbr(self, *nodes):
        '''
        Calculate the MBR for a list of nodes.
        '''
        total = None
        for mbr, _ in nodes:
            if total is None:
                total = mbr
            else:
                total = self._merge(total, mbr)
        return total

    def delete_point(self, x, y, value=None, match=MatchType.EQUAL):
        '''
        Remove all entries that match the given point and optional value.

        Returns the number of items deleted.
        To preview which items are deleted, call `get_point()` with the same parameters,
        '''
        return self._delete_normalized_mbr((x, y, x, y), value, match)

    def delete_box(self, x1, y1, x2, y2, value=None, match=MatchType.EQUAL):
        '''
        Remove all entries that match the given box and optional value.

        Returns the number of items deleted.
        To preview which items are deleted, call `get_point()` with the same parameters,
        '''
        return self._delete_normalized_mbr(self._normalize_mbr(x1, y1, x2, y2), value, match)

    def _delete_normalized_mbr(self, mbr, value, match):
        '''
        Internal deletion.
        '''
        count = 0
        for _, mbr_match in self._get_normalized_box(mbr, value, match):
            # root cannot be empty as it contains mbr
            found = self._delete_node(self._root, mbr_match, value)
            if found:
                delete, inserts = found
                if delete:
                    self._root = None
                self._reinsert(inserts)
                count += 1
                self._size -= 1
            else:
                raise Exception('Failed to delete %s' % mbr_match)
            if self._root and len(self._root[1]) == 1 and self._root[0]:  # single child, not leaf
                self._root = self._root[1][0][1]  # contents of first child
        return count

    def _delete_node(self, node, mbr, value):
        '''
        Internal deletion from or below the given node.
        '''
        height, data = node
        for i, (mbr_node, contents_node) in enumerate(data):
            if height:
                if self._contains(mbr_node, mbr):
                    found = self._delete_node(contents_node, mbr, value)
                    if found:
                        delete, inserts = found
                        if delete:
                            del data[i]
                            if len(data) < self._min:
                                for node in data:
                                    inserts.append((height, *node))
                                return True, inserts
                        else:
                            # something under data[i] has been deleted so recalculate mbr
                            old_mbr, (height_children, children) = data[i]
                            new_mbr = self._calculate_mbr(*children)
                            data[i] = (new_mbr, (height_children, children))
                        return False, inserts
            else:
                if mbr_node == mbr and (value is None or value == contents_node):
                    del data[i]
                    if len(data) < self._min:
                        return True, [(0, *node) for node in data]
                    else:
                        return False, []

    def _leaves(self, node):
        '''
        Iterator over the leaves in a node.
        '''
        height, data = node
        for mbr, child in data:
            if height:
                yield from self._leaves(child)
            else:
                yield mbr, child

    def _reinsert(self, inserts):
        '''
        Reinsert sub-trees (including leaves) removed during re-arrangement on deletion.

        We try to insert whole sub-trees, but this is not always possible (if the height has changed)
        (this has a barely measurable effect on performance, but seems to be what the original paper expected).
        '''
        if self._root:
            max_height = self._root[0]
        else:
            max_height = 0
        for insert in inserts:
            if insert[0] > max_height:
                for mbr, value in self._leaves(insert[2]):
                    self._add_normalized_mbr(0, mbr, value)
            else:
                self._add_normalized_mbr(*insert)

    def __len__(self):
        '''
        Expose number of entries though usual Python API.
        '''
        return self._size

    # utilities for debugging

    def dump(self):
        '''
        An iterator over the tree structure.
        '''
        if self._root:
            height, data = self._root
            yield height + 1, self._calculate_mbr(*data), None  # implied mbr on all nodes
            yield from self._dump(self._root)

    def _dump(self, node):
        '''
        Internal iterator over the tree structure.
        '''
        height, data = node
        for mbr, value in data:
            yield height, mbr, None if height else value
            if height:
                yield from self._dump(value)

    def print(self):
        '''
        Dump the tree structure to stdout for debugging.
        '''
        for height, mbr, value in self.dump():
            print('%2d %s (%4.2f, %4.2f, %4.2f, %4.2f) %s' %
                  (height, ' ' * (10 - height), *mbr, '' if value is None else value))

    def assert_consistent(self):
        '''
        Make some basic tests of consistency.
        '''
        if self._size and not self._root:
            raise Exception('Emtpy root (and size %d)' % self._size)
        size = self._assert_consistent(self._root)
        if size != self._size:
            raise Exception('Unexpected number of leaves (%d != %d)' % (size, self._size))

    def _assert_consistent(self, node):
        '''
        Internal tests of consistency.
        '''
        if node:
            height, data = node
            if len(data) < self._min and node != self._root:
                raise Exception('Too few children at height %d' % height)
            if len(data) > self._max:
                raise Exception('Too many children at height %d' % height)
            if height:
                count = 0
                for mbr, child in data:
                    (height_child, data_child) = child
                    mbr_check = self._calculate_mbr(*data_child)
                    if mbr_check != mbr:
                        raise Exception('Bad MBR at height %d %s / %s' % (height, mbr_check, mbr))
                    count += self._assert_consistent(child)
                return count
            else:
                return len(data)
        else:
            return 0

    # allow different coordinate systems

    @abstractmethod
    def _normalize_mbr(self, x1, y1, x2, y2):
        raise NotImplementedError()

    @abstractmethod
    def _intersect(self, mbr1, mbr2):
        raise NotImplementedError()

    @abstractmethod
    def _contains(self, outer, inner):
        raise NotImplementedError()

    @abstractmethod
    def _area(self, mbr):
        raise NotImplementedError()

    @abstractmethod
    def _merge(self, mbr1, mbr2):
        raise NotImplementedError()

    # allow different split algorithms

    @abstractmethod
    def _pick_linear_seeds(self, data):
        raise NotImplementedError()

    @abstractmethod
    def _split(self, height, data):
        raise NotImplementedError()


class CartesianMixin:

    def _normalize_mbr(self, x1, y1, x2, y2):
        '''
        Return xy_bottom_left, xy_top_right for cartesian coordinates.
        '''
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def _intersect(self, mbr1, mbr2):
        '''
        Do the two MBR's intersect?
        '''
        x1, y1, x2, y2 = mbr1
        X1, Y1, X2, Y2 = mbr2
        return x1 <= X2 and x2 >= X1 and y1 <= Y2 and y2 >= Y1

    def _contains(self, outer, inner):
        '''
        Is the `inner` MBR contained by the `outer`?
        '''
        x1, y1, x2, y2 = outer
        X1, Y1, X2, Y2 = inner
        return x1 <= X1 and x2 >= X2 and y1 <= Y1 and y2 >= Y2

    def _area(self, mbr):
        '''
        Area of the MBR
        '''
        x1, y1, x2, y2 = mbr
        return (x2 - x1) * (y2 - y1)

    def _merge(self, mbr1, mbr2):
        '''
        Construct the MBR That contains both the given MBRs.
        '''
        x1, y1, x2, y2 = mbr1
        X1, Y1, X2, Y2 = mbr2
        return min(x1, X1), min(y1, Y1), max(x2, X2), max(y2, Y2)

    def __extremes(self, data):
        '''
        Internal routine for linear seeds.

        Measure the lowest higher bound, left-most right bound, etc, from a collection of MBRs
        and records which MRB (index) is responsible for each.
        '''
        index, extreme = None, None
        for i, (mbr, _) in enumerate(data):
            if not i:
                index = [0, 0, 0, 0]
                extreme = list(mbr)
            else:
                for j in range(2):
                    if mbr[j] > extreme[j]:   # want max of lower left
                        extreme[j] = mbr[j]
                        index[j] = i
                    if mbr[j+2] < extreme[j+2]:  # and min of upper right
                        extreme[j+2] = mbr[j+2]
                        index[j+2] = i
        return index, extreme

    def _pick_linear_seeds(self, data):
        '''
        Choose the two MBRs that are most distance.

        Only called from LinearSplitMixin.
        '''
        global_mbr = self._calculate_mbr(*self._root[1])
        norm_x, norm_y = global_mbr[2] - global_mbr[0], global_mbr[3] - global_mbr[1]
        norm = [norm_x, norm_y, norm_x, norm_y]
        index, extremes = self.__extremes(data)
        extremes = [x / n for x, n in zip(extremes, norm)]
        if extremes[2] - extremes[0] > extremes[3] - extremes[1] and index[0] != index[2]:
            return index[0], index[2]
        elif extremes[2] - extremes[0] < extremes[3] - extremes[1] and index[1] != index[3]:
            return index[1], index[3]
        else:
            return 0, 1  # degenerate case :(


class LinearSplitMixin:

    def _split(self, height, nodes):
        '''
        Divide the nodes into two,
        '''
        i, j = self._pick_linear_seeds(nodes)
        split = [(nodes[i][0], (height, [nodes[i]])), (nodes[j][0], (height, [nodes[j]]))]
        del nodes[max(i, j)]
        del nodes[min(i, j)]
        # ugliness below is rebuilding tuple with new mbr
        while nodes:
            if len(nodes) < self._min:
                for index in 0, 1:
                    if len(split[index][1][1]) + len(nodes) == self._min:
                        split[index][1][1].extend(nodes)
                        split[index] = (self._calculate_mbr(*split[index][1][1]), split[index][1])
                        return split
            node = nodes.pop()
            index, mbr = self._best(split, node[0], height)
            split[index] = (mbr, split[index][1])  # insert mbr, but it's a tuple, so need to rewrite
            split[index][1][1].append(node)
        return split


class QuadraticSplitMixin:

    def _split(self, height, data):
        pass


class CLRTree(LinearSplitMixin, CartesianMixin, BaseTree): pass

