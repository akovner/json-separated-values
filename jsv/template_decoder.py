from enum import Enum, auto, unique
from re import compile
import json
from collections import OrderedDict


@unique
class TemplateStates(Enum):
    DONE = auto()
    EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE = auto()
    EXPECT_ARRAY_OR_OBJECT = auto()
    ARRAY_NEXT_OR_CLOSE = auto()
    OBJECT_AFTER_KEY = auto()
    OBJECT_NEXT_OR_CLOSE = auto()
    EXPECT_QUOTE = auto()


@unique
class StringStates(Enum):
    STRING_NEXT_OR_CLOSE = auto()
    STRING_ESCAPE = auto()
    STRING_HEX = auto()


@unique
class RecordExpectedStates(Enum):
    EXPECT_OBJECT_START = auto()
    EXPECT_OBJECT_END = auto()
    EXPECT_ARRAY_START = auto()
    EXPECT_ARRAY_END = auto()
    EXPECT_VALUE = auto()
    EXPECT_COMMA = auto()


@unique
class RecordStates(Enum):
    EXPECT_OBJECT_START = auto()
    EXPECT_NEXT_OBJECT = auto()
    EXPECT_NEXT_OR_OBJECT_END = auto()
    EXPECT_ARRAY_START = auto()
    EXPECT_NEXT_ARRAY = auto()
    EXPECT_NEXT_OR_ARRAY_END = auto()
    EXPECT_VALUE = auto()
    DONE = auto()


@unique
class ParentStates(Enum):
    ARRAY = auto()
    OBJECT = auto()
    NONE = auto()


hex_re = compile('[0-9a-fA-F]')


def append_string(arr, char):
            if arr and isinstance(arr[-1], list):
                arr[-1].append(char)
            else:
                arr.append([char])


def encode_objects(rs):
    stack = []

    for t in rs:
        if t[0] is RecordExpectedStates.EXPECT_ARRAY_START:
            array_def = []
            if t[1] is ParentStates.OBJECT:
                stack[-1].update({t[2]: array_def})
            elif t[1] is ParentStates.ARRAY:
                stack[-1].append(array_def)
            stack.append(array_def)
        elif t[0] is RecordExpectedStates.EXPECT_ARRAY_END:
            out = stack.pop()
        elif t[0] is RecordExpectedStates.EXPECT_OBJECT_START:
            object_def = OrderedDict()
            if t[1] is ParentStates.OBJECT:
                stack[-1].update({t[2]: object_def})
            elif t[1] is ParentStates.ARRAY:
                stack[-1].append(object_def)
            stack.append(object_def)
        elif t[0] is RecordExpectedStates.EXPECT_OBJECT_END:
            out = stack.pop()
        elif t[0] is RecordExpectedStates.EXPECT_VALUE:
            value_def = None
            if t[1] is ParentStates.OBJECT:
                stack[-1].update({t[2]: value_def})
            elif t[1] is ParentStates.ARRAY:
                stack[-1].append(value_def)

    return out


def json_remainder(s_array):
    s = ''.join(reversed(s_array))
    start_len = len(s)
    s = s.lstrip()
    end_len = len(s)
    d = json.JSONDecoder()
    v, r = d.raw_decode(s)
    for i in range(r + start_len - end_len):
        s_array.pop()
    return v


def err_msg(msg, i, c):
    return '{0} @ index: {1}, character: {2}'.format(msg, i, c)


def get_json_value(char_list):
    return json_remainder(char_list)


def get_json_string(char_list):
    state = StringStates.STRING_NEXT_OR_CLOSE
    string_array = []
    i = -1

    while True:
        try:
            i += 1
            current_char = char_list.pop()
        except IndexError:
            raise IndexError(err_msg('End of string reached unexpectedly', i, current_char))

        # ---------------------------
        # State: STRING_NEXT_OR_CLOSE
        # ---------------------------
        if state is StringStates.STRING_NEXT_OR_CLOSE:
            if current_char == '"':
                return ''.join(string_array)
            elif current_char == '\\':
                state = StringStates.STRING_ESCAPE
            else:
                string_array.append(current_char)

        # --------------------
        # State: STRING_ESCAPE
        # --------------------
        elif state is StringStates.STRING_ESCAPE:
            if current_char == '"':
                string_array.append('"')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == '\\':
                string_array.append('\\')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == '/':
                string_array.append('/')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == 'b':
                string_array.append('\b')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == 'f':
                string_array.append('\f')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == 'n':
                string_array.append('\n')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == 'r':
                string_array.append('\r')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == 't':
                string_array.append('\t')
                state = StringStates.STRING_NEXT_OR_CLOSE
            elif current_char == 'u':
                hex_array = []
                state = StringStates.STRING_HEX
            else:
                raise ValueError(err_msg('expecting valid escape character', i, current_char))

        # -----------------
        # State: STRING_HEX
        # -----------------
        elif state is StringStates.STRING_HEX:
            if hex_re.search(current_char):
                hex_array.append(current_char)
                if len(hex_array) >= 4:
                    string_array.append(bytearray.fromhex(''.join(hex_array)).decode())
                    state = StringStates.STRING_NEXT_OR_CLOSE
                else:
                    hex_array.append(current_char)
            else:
                raise ValueError(err_msg('Expected a hex character ([0-9A-Fa-f])', i, current_char))


def get_key_value_pair(char_list):
    current_char = ''
    while current_char != '"':
        try:
            current_char = char_list.pop()
        except IndexError:
            raise IndexError('error')

        if not current_char.isspace() and not current_char == '"':
            raise ValueError('error')

    k = get_json_string(char_list)

    current_char = ''
    while current_char != ':':
        try:
            current_char = char_list.pop()
        except IndexError:
            raise IndexError('error')

        if not current_char.isspace() and not current_char == ':':
            raise ValueError('error')

    v = get_json_value(char_list)
    return k, v


def ws_trim(char_list):
    if char_list[-1].isspace():
        char_list.pop()


class DecodeStates(Enum):
    OBJECT_START = auto()
    OBJECT_KEYS = auto()
    OBJECT_END = auto()
    ARRAY_START = auto()
    ARRAY_BODY = auto()
    ARRAY_TAIL = auto()
    ARRAY_END = auto()
    VALUE = auto()


class Template:
    def encode(self, obj):
        fm = self._fill_map

        if isinstance(fm, OrderedDict):
            return self._encode_obj(obj, fm)
        elif isinstance(fm, list):
            return self._encode_list(obj, fm)
        else:
            return self._json_encode(obj)

    def _encode_obj(self, obj, fm):
        if not isinstance(obj, dict):
            raise ValueError('Expecting a dictionary')

        entries = [''] * len(fm)
        indexes = list(fm.keys())
        for k, v in obj.items():
            if k in fm:
                child_fm = fm[k]
                if isinstance(child_fm, OrderedDict):
                    entries[indexes.index(k)] = self._encode_obj(v, child_fm)
                elif isinstance(child_fm, list):
                    entries[indexes.index(k)] = self._encode_list(v, child_fm)
                else:
                    entries[indexes.index(k)] = self._json_encode(v)
            else:
                entries.append('"{0}":{1}'.format(k, self._json_encode(v)))

        return '{{{}}}'.format(','.join(entries))

    def _encode_list(self, arr, fm):
        if not isinstance(arr, list):
            raise ValueError('Expecting a list')

        entries = []
        for i, v in enumerate(arr):
            if i < len(fm):
                child_fm = fm[i]
            else:
                child_fm = fm[-1]
            if isinstance(child_fm, OrderedDict):
                entries.append(self._encode_obj(v, child_fm))
            elif isinstance(child_fm, list):
                entries.append(self._encode_list(v, child_fm))
            else:
                entries.append(self._json_encode(v))

        return '[{}]'.format(','.join(entries))

    def parse_record(self, s):
        stack = []
        char_list = list(reversed(s))
        j = 0
        i = -1
        rs = self._record_states
        current_char = None

        while True:
            try:
                i += 1
                current_char = char_list.pop()
            except IndexError:
                raise IndexError(err_msg('End of string reached unexpectedly', i, current_char))

            if rs[j][0] is RecordExpectedStates.EXPECT_ARRAY_START:
                if current_char.isspace():
                    pass
                elif current_char == '[':
                    stack.append([])
                    ws_trim(char_list)
                    if char_list[-1] == ']':
                        j = rs[j][2]
                    else:
                        j += 1
                else:
                    raise ValueError('error')

            elif rs[j][0] is RecordExpectedStates.EXPECT_ARRAY_END:
                if current_char.isspace():
                    pass
                elif current_char == ']':
                    tmp = stack.pop()
                    if rs[j][1] is ParentStates.ARRAY:
                        stack[-1].append(tmp)
                    elif rs[j][1] is ParentStates.OBJECT:
                        key = rs[j][2]
                        stack[-1][key] = tmp
                    else:
                        return tmp
                    j += 1
                elif current_char == ',':
                    j = rs[j][-1]

            elif rs[j][0] is RecordExpectedStates.EXPECT_OBJECT_START:
                if current_char.isspace():
                    pass
                elif current_char == '{':
                    stack.append({})
                    j += 1
                else:
                    raise ValueError('error')

            elif rs[j][0] is RecordExpectedStates.EXPECT_OBJECT_END:
                if current_char.isspace():
                    pass
                elif current_char == '}':
                    tmp = stack.pop()
                    if rs[j][1] is ParentStates.ARRAY:
                        stack[-1].append(tmp)
                    elif rs[j][1] is ParentStates.OBJECT:
                        key = rs[j][2]
                        stack[-1][key] = tmp
                    else:
                        return tmp
                    j += 1
                elif current_char == ',':
                    k, v = get_key_value_pair(char_list)
                    stack[-1][k] = v
                else:
                    raise ValueError('error')

            elif rs[j][0] is RecordExpectedStates.EXPECT_VALUE:
                if current_char:
                    char_list.append(current_char)
                tmp = get_json_value(char_list)
                if rs[j][1] is ParentStates.ARRAY:
                    stack[-1].append(tmp)
                elif rs[j][1] is ParentStates.OBJECT:
                    key = rs[j][2]
                    stack[-1][key] = tmp
                else:
                    return tmp
                j += 1

            elif rs[j][0] is RecordExpectedStates.EXPECT_COMMA:
                if current_char.isspace():
                    pass
                elif current_char == ',':
                    j += 1
                elif rs[j][1] is ParentStates.ARRAY and current_char == ']':
                    j = rs[j][2]
                    char_list.append(']')
                else:
                    raise ValueError('Error')

    @property
    def remainder(self):
        return self._remainder

    def __eq__(self, other):
        return self._root == other

    def __init__(self, s):

        self._json_encode = json.JSONEncoder(separators=(',', ':')).encode

        if isinstance(s, str):
            state = TemplateStates.EXPECT_ARRAY_OR_OBJECT
            char_list = list(reversed(s))
            array_stack = []
            array_list = []
            parent_stack = []
            record_states = []
            key_stack = []
            i = -1
            current_char = None

            while state is not TemplateStates.DONE:
                try:
                    current_char = char_list.pop()
                except IndexError:
                    raise IndexError(err_msg('End of string reached unexpectedly', i, current_char))
                i += 1

                # --------------------------------------------
                # State: EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE
                # --------------------------------------------
                if state is TemplateStates.EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE:
                    if current_char.isspace():
                        pass
                    elif current_char == '{':
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.ARRAY:
                                array_stack[-1].append(len(record_states))
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_START,
                                                      ParentStates.ARRAY))
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_START,
                                                      ParentStates.OBJECT,
                                                      key_stack[-1]))
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_OBJECT_START,
                                                  ParentStates.NONE))
                        parent_stack.append(ParentStates.OBJECT)
                        state = TemplateStates.EXPECT_QUOTE
                    elif current_char == '[':
                        array_stack.append([len(record_states)])
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.ARRAY:
                                array_stack[-2].append(len(record_states))
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_START,
                                                      ParentStates.ARRAY))
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_START,
                                                      ParentStates.OBJECT,
                                                      key_stack[-1]))
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_ARRAY_START,
                                                  ParentStates.NONE))
                        parent_stack.append(ParentStates.ARRAY)
                    elif current_char == ',':
                        if parent_stack and parent_stack[-1] is ParentStates.ARRAY:
                            array_stack[-1].append(len(record_states))
                        record_states.append((RecordExpectedStates.EXPECT_VALUE,
                                              ParentStates.ARRAY))
                        record_states.append((RecordExpectedStates.EXPECT_COMMA,
                                              ParentStates.ARRAY))
                    elif current_char == ']':
                        array_stack[-1].append(len(record_states))
                        array_stack[-1].append(len(record_states)+1)
                        array_list.append(array_stack.pop())
                        parent_stack.pop()
                        record_states.append((
                            RecordExpectedStates.EXPECT_VALUE,
                            ParentStates.ARRAY))
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.OBJECT:
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_END,
                                                      ParentStates.OBJECT,
                                                      key_stack.pop()))
                                state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_END,
                                                      ParentStates.ARRAY))
                                state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_ARRAY_END,
                                                  ParentStates.NONE))
                            state = TemplateStates.DONE
                    else:
                        raise ValueError(err_msg('Expecting `{`, `[` or `]`', i, current_char))

                # -----------------------------
                # State: EXPECT_ARRAY_OR_OBJECT
                # -----------------------------
                elif state is TemplateStates.EXPECT_ARRAY_OR_OBJECT:
                    if current_char.isspace():
                        pass
                    elif current_char == '{':
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.ARRAY:
                                array_stack[-1].append(len(record_states))
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_START,
                                                      ParentStates.ARRAY))
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_START,
                                                      ParentStates.OBJECT,
                                                      key_stack[-1]))
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_OBJECT_START,
                                                  ParentStates.NONE))
                        parent_stack.append(ParentStates.OBJECT)
                        state = TemplateStates.EXPECT_QUOTE
                    elif current_char == '[':
                        array_stack.append([len(record_states)])
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.ARRAY:
                                array_stack[-2].append(len(record_states))
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_START,
                                                      ParentStates.ARRAY))
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_START,
                                                      ParentStates.OBJECT,
                                                      key_stack[-1]))
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_ARRAY_START,
                                                  ParentStates.NONE))
                        parent_stack.append(ParentStates.ARRAY)
                        state = TemplateStates.EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE
                    else:
                        raise ValueError(err_msg('Expecting `{` or `[`', i, current_char))

                # --------------------------
                # State: ARRAY_NEXT_OR_CLOSE
                # --------------------------
                elif state is TemplateStates.ARRAY_NEXT_OR_CLOSE:
                    if current_char.isspace():
                        pass
                    elif current_char == ',':
                        record_states.append((RecordExpectedStates.EXPECT_COMMA,
                                              ParentStates.ARRAY))
                        state = TemplateStates.EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE
                    elif current_char == ']':
                        array_stack[-1].append(len(record_states))
                        array_list.append(array_stack.pop())
                        parent_stack.pop()
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.OBJECT:
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_END,
                                                      ParentStates.OBJECT,
                                                      key_stack.pop()))
                                state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_ARRAY_END,
                                                      ParentStates.ARRAY))
                                state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_ARRAY_END,
                                                  ParentStates.NONE))
                            state = TemplateStates.DONE
                    else:
                        raise ValueError(err_msg('Expecting `,` or `]`', i, current_char))

                # -----------------------
                # State: OBJECT_AFTER_KEY
                # -----------------------
                elif state is TemplateStates.OBJECT_AFTER_KEY:
                    if current_char.isspace():
                        pass
                    elif current_char == ',':
                        record_states.append((RecordExpectedStates.EXPECT_VALUE,
                                              ParentStates.OBJECT,
                                              key_stack.pop()))
                        record_states.append((RecordExpectedStates.EXPECT_COMMA,
                                              ParentStates.OBJECT))
                        state = TemplateStates.EXPECT_QUOTE
                    elif current_char == ':':
                        state = TemplateStates.EXPECT_ARRAY_OR_OBJECT
                    elif current_char == '}':
                        parent_stack.pop()
                        record_states.append((RecordExpectedStates.EXPECT_VALUE,
                                              ParentStates.OBJECT,
                                              key_stack.pop()))
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.OBJECT:
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_END,
                                                      ParentStates.OBJECT,
                                                      key_stack.pop()))
                                state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_END,
                                                      ParentStates.ARRAY))
                                state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_OBJECT_END,
                                                  ParentStates.NONE))
                            state = TemplateStates.DONE
                    else:
                        raise ValueError(err_msg('Expecting `,`, `:`, or `}`', i, current_char))

                # ---------------------------
                # State: OBJECT_NEXT_OR_CLOSE
                # ---------------------------
                elif state is TemplateStates.OBJECT_NEXT_OR_CLOSE:
                    if current_char.isspace():
                        pass
                    elif current_char == ',':
                        record_states.append((RecordExpectedStates.EXPECT_COMMA,
                                              ParentStates.OBJECT))
                        state = TemplateStates.EXPECT_QUOTE
                    elif current_char == '}':
                        parent_stack.pop()
                        if parent_stack:
                            if parent_stack[-1] is ParentStates.ARRAY:
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_END,
                                                      ParentStates.ARRAY))
                                state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                            else:
                                record_states.append((RecordExpectedStates.EXPECT_OBJECT_END,
                                                      ParentStates.OBJECT,
                                                      key_stack.pop()))
                        else:
                            record_states.append((RecordExpectedStates.EXPECT_OBJECT_END,
                                                  ParentStates.NONE))
                            state = TemplateStates.DONE
                    else:
                        raise ValueError(err_msg('Expecting `,` or `}`', i, current_char))

                # -------------------
                # State: EXPECT_QUOTE
                # -------------------
                elif state is TemplateStates.EXPECT_QUOTE:
                    if current_char.isspace():
                        pass
                    elif current_char == '"':
                        key_str = get_json_string(char_list)
                        key_stack.append(key_str)
                        state = TemplateStates.OBJECT_AFTER_KEY
                    elif current_char == '}':
                        raise ValueError(err_msg('Object must contain at least 1 key', i, current_char))
                    else:
                        raise ValueError(err_msg('Expecting `"`', i, current_char))
        else:
            raise TypeError('Expecting a string')

        self._remainder = ''.join(reversed(char_list))

        # include index of last value entry in an array in the token
        for array in array_list:
            record_states[array[-1]] = record_states[array[-1]] + (array[-2],)

        # include index of array end in commas and array starts
        for array in array_list:
            array_end_index = array[-1]
            array_start_index = array[0]
            record_states[array_start_index] = record_states[array_start_index] + (array_end_index,)
            for comma in map(lambda x: x - 1, array[2:-1]):
                record_states[comma] = record_states[comma] + (array_end_index,)

        # delete superfluous array entries
        delete_indexes = set()
        for array in array_list:
            array_iter = zip(array[-2::-1], array[-1:1:-1])
            a, b = next(array_iter)
            ref_tuple = tuple(record_states[a:b]) + ((RecordExpectedStates.EXPECT_COMMA, ParentStates.ARRAY),)
            for a, b in array_iter:
                if ref_tuple == tuple(record_states[a:b]):
                    for ind in range(a, b):
                        delete_indexes.add(ind)
                else:
                    break
        for ind in range(len(record_states) - 1, -1, -1):
            if ind in delete_indexes:
                record_states.pop(ind)

        # delete empty arrays
        start_index = None
        value_index = None
        delete_list = []
        for i, s in enumerate(record_states):
            if start_index is None:
                if s[0] is RecordExpectedStates.EXPECT_ARRAY_START:
                    start_index = i
            elif value_index is None:
                if s[0] is RecordExpectedStates.EXPECT_ARRAY_START:
                    pass
                elif s[0] is RecordExpectedStates.EXPECT_VALUE:
                    value_index = i
                else:
                    start_index = None
            else:
                if s[0] is not RecordExpectedStates.EXPECT_ARRAY_END:
                    end_index = i - 1
                    if i > end_index:
                        radius = min(value_index - start_index, end_index - value_index)
                        for j in range(value_index - radius, value_index + radius + 1):
                            if j == value_index:
                                end_token = record_states[j + radius]
                                if end_token[1] is ParentStates.OBJECT:
                                    record_states[j] = (RecordExpectedStates.EXPECT_VALUE,
                                                        end_token[1],
                                                        end_token[2])
                                else:
                                    record_states[j] = (RecordExpectedStates.EXPECT_VALUE,
                                                        end_token[1])
                            else:
                                delete_list.append(j)
                    start_index = None
                    value_index = None
        for ind in delete_list[::-1]:
            record_states.pop(ind)

        self._record_states = tuple(record_states)
        self._fill_map = encode_objects(self._record_states)


if __name__ == '__main__':
    t = Template('[[{"key_1"}]]')