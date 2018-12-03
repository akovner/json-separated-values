import json
from collections import OrderedDict
from enum import unique, Enum, auto
from re import compile


class Template:
    def __repr__(self):
        if isinstance(self._key_tree, list):
            return encode_template_list(self._key_tree)
        elif isinstance(self._key_tree, OrderedDict):
            return encode_template_dict(self._key_tree)
        else:
            return '{}'

    def __init__(self, s):
        if isinstance(s, str):
            template_str = s
        elif isinstance(s, dict) or isinstance(s, list) or s is None:
            template_str = get_template_str(s)
        self._key_tree = parse_template_string(template_str)

    def encode(self, obj):
        c = self._key_tree

        if isinstance(c, OrderedDict):
            return encode_dict(obj, c)
        elif isinstance(c, list):
            return encode_list(obj, c)
        else:
            return self._json_encode(obj)

    def decode(self, s):
        c = self._key_tree
        char_list = list(reversed(s))

        if c is None:
            return get_json_value(char_list)
        if isinstance(c, list):
            out = []
            it = iter(c)
            decode_array_entries(char_list, out, it)
            return out
        else:
            out = {}
            it = iter(c.items())
            decode_dict_entries(char_list, out, it)
            return out


def encode_dict(obj, fm):
    if not isinstance(obj, dict):
        raise ValueError('Expecting a dictionary')

    entries = [''] * len(fm)
    indexes = list(fm.keys())
    for k, v in obj.items():
        if k in fm:
            child_fm = fm[k]
            if isinstance(child_fm, OrderedDict):
                entries[indexes.index(k)] = encode_dict(v, child_fm)
            elif isinstance(child_fm, list):
                entries[indexes.index(k)] = encode_list(v, child_fm)
            else:
                entries[indexes.index(k)] = json_encode(v)
        else:
            entries.append('"{0}":{1}'.format(k, json_encode(v)))

    return '{{{}}}'.format(','.join(entries))


def encode_list(arr, fm):
    if not isinstance(arr, list):
        raise ValueError('Expecting a list')

    entries = []
    for i, v in enumerate(arr):
        if i < len(fm):
            child_fm = fm[i]
        else:
            child_fm = fm[-1]
        if isinstance(child_fm, OrderedDict):
            entries.append(encode_dict(v, child_fm))
        elif isinstance(child_fm, list):
            entries.append(encode_list(v, child_fm))
        else:
            entries.append(json_encode(v))

    return '[{}]'.format(','.join(entries))


def decode_dict_entries(char_list, obj, it):

    consume_next(char_list, {'{'})
    try:
        k, v = next(it)
    except StopIteration:
        raise ValueError('unexpected error')

    ws_trim(char_list)
    if char_list[-1] != ',':
        if v is None:
            obj[k] = get_json_value(char_list)
        elif isinstance(v, list):
            n = []
            obj[k] = n
            it_next = iter(v)
            decode_array_entries(char_list, n, it_next)
        else:
            n = {}
            obj[k] = n
            it_next = iter(v.items())
            decode_dict_entries(char_list, n, it_next)

    for k, v in it:
        consume_next(char_list, {','})
        ws_trim(char_list)
        if char_list[-1] != ',':
            if v is None:
                obj[k] = get_json_value(char_list)
            elif isinstance(v, list):
                n = []
                obj[k] = n
                it_next = iter(v)
                decode_array_entries(char_list, n, it_next)
            else:
                n = {}
                obj[k] = n
                it_next = iter(v.items())
                decode_dict_entries(char_list, n, it_next)

    while True:
        if consume_next(char_list, {'}', ','}) == '}':
            break
        k, v = get_key_value_pair(char_list)
        obj[k] = v


def decode_array_entries(char_list, arr, it):

    consume_next(char_list, {'['})
    try:
        c = next(it)
    except StopIteration:
        raise ValueError('Unexpected error')

    ws_trim(char_list)
    if char_list[-1] == ']':
        return

    if c is None:
        arr.append(get_json_value(char_list))
    elif isinstance(c, list):
        n = []
        arr.append(n)
        it_next = iter(c)
        decode_array_entries(char_list, n, it_next)
    else:
        n = {}
        arr.append(n)
        it_next = iter(c.items())
        decode_dict_entries(char_list, n, it_next)

    for c in it:
        if consume_next(char_list, {',', ']'}) == ']':
            return
        if c is None:
            arr.append(get_json_value(char_list))
        elif isinstance(c, list):
            n = []
            arr.append(n)
            it_next = iter(c)
            decode_array_entries(char_list, n, it_next)
        else:
            n = {}
            arr.append(n)
            it_next = iter(c.items())
            decode_dict_entries(char_list, n, it_next)

    while True:
        if consume_next(char_list, {']', ','}) == ']':
            break
        if c is None:
            arr.append(get_json_value(char_list))
        elif isinstance(c, list):
            n = []
            arr.append(n)
            it_next = iter(c)
            decode_array_entries(char_list, n, it_next)
        else:
            n = {}
            arr.append(n)
            it_next = iter(c.items())
            decode_dict_entries(char_list, n, it_next)


def encode_template_dict(kt):
    out_arr = []
    for k, v in kt.items():
        if v:
            if isinstance(v, list):
                out_arr.append('"{0}":{1}'.format(k, encode_template_list(v)))
            else:
                out_arr.append('"{0}":{1}'.format(k, encode_template_dict(v)))
        else:
            out_arr.append('"{}"'.format(k))

    return '{{{}}}'.format(','.join(out_arr))


def encode_template_list(kt):
    out_arr = []
    for v in kt:
        if v:
            if isinstance(v, list):
                out_arr.append(encode_template_list(v))
            else:
                out_arr.append(encode_template_dict(v))
        else:
            out_arr.append('')

    return '[{}]'.format(','.join(out_arr))


@unique
class TemplateStates(Enum):
    DONE = auto()
    EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE = auto()
    EXPECT_ARRAY_OR_OBJECT = auto()
    ARRAY_NEXT_OR_CLOSE = auto()
    OBJECT_AFTER_KEY = auto()
    OBJECT_NEXT_OR_CLOSE = auto()
    EXPECT_QUOTE = auto()


def parse_template_string(s):
    state = TemplateStates.EXPECT_ARRAY_OR_OBJECT
    char_list = list(reversed(s))
    val = None
    i = -1
    current_char = None
    stack = []
    has_keys = []

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
                stack.append(OrderedDict())
                has_keys.append(False)
                state = TemplateStates.EXPECT_QUOTE
            elif current_char == '[':
                stack.append([])
                has_keys.append(False)
            elif current_char == ',':
                stack[-1].append(None)
            elif current_char == ']':
                stack[-1].append(None)
                if has_keys.pop():
                    val = stack.pop()
                    prune_array_end(val)
                else:
                    stack.pop()
                    val = None
                if stack:
                    if isinstance(stack[-1], list):
                        stack[-1].append(val)
                        state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                    else:
                        key = stack.pop()
                        stack[-1].update({key: val})
                        state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                else:
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
                stack.append(OrderedDict())
                has_keys.append(False)
                state = TemplateStates.EXPECT_QUOTE
            elif current_char == '[':
                stack.append([])
                has_keys.append(False)
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
                state = TemplateStates.EXPECT_ARRAY_OR_OBJECT_OR_ARRAY_CLOSE
            elif current_char == ']':
                if has_keys.pop():
                    val = stack.pop()
                    prune_array_end(val)
                else:
                    stack.pop()
                    val = None
                if stack:
                    if isinstance(stack[-1], list):
                        stack[-1].append(val)
                        state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                    else:
                        key = stack.pop()
                        stack[-1].update({key: val})
                        state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                else:
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
                key = stack.pop()
                stack[-1].update({key: None})
                state = TemplateStates.EXPECT_QUOTE
            elif current_char == ':':
                state = TemplateStates.EXPECT_ARRAY_OR_OBJECT
            elif current_char == '}':
                key = stack.pop()
                val = stack.pop()
                has_keys.pop()
                val.update({key: None})
                if stack:
                    if isinstance(stack[-1], list):
                        stack[-1].append(val)
                        state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                    else:
                        key = stack.pop()
                        stack[-1].update({key: val})
                        state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                else:
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
                state = TemplateStates.EXPECT_QUOTE
            elif current_char == '}':
                val = stack.pop()
                val = val if has_keys.pop() else None
                if stack:
                    if isinstance(stack[-1], list):
                        stack[-1].append(val)
                        state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                    else:
                        key = stack.pop()
                        stack[-1].update({key: val})
                else:
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
                stack.append(get_json_string(char_list))
                state = TemplateStates.OBJECT_AFTER_KEY
                has_keys = [True] * len(has_keys)
            elif current_char == '}':
                val = None
                stack.pop()
                has_keys.pop()
                if stack:
                    if isinstance(stack[-1], list):
                        stack[-1].append(val)
                        state = TemplateStates.ARRAY_NEXT_OR_CLOSE
                    else:
                        key = stack.pop()
                        stack[-1].update({key: val})
                        state = TemplateStates.OBJECT_NEXT_OR_CLOSE
                else:
                    state = TemplateStates.DONE
            else:
                raise ValueError(err_msg('Expecting `"`', i, current_char))

    return val


def get_json_value(char_list):
    s = ''.join(reversed(char_list))
    start_len = len(s)
    s = s.lstrip()
    end_len = len(s)
    d = json.JSONDecoder()
    v, r = d.raw_decode(s)
    for i in range(r + start_len - end_len):
        char_list.pop()
    return v


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


@unique
class StringStates(Enum):
    STRING_NEXT_OR_CLOSE = auto()
    STRING_ESCAPE = auto()
    STRING_HEX = auto()


def get_json_string(char_list):
    state = StringStates.STRING_NEXT_OR_CLOSE
    string_array = []
    current_char = None
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


def get_template_str(obj):
    if not obj:
        return None

    if isinstance(obj, dict):
        return obj_to_template_str(obj)
    elif isinstance(obj, list):
        return arr_to_template_str(obj)

    raise ValueError('Expecting object or array')


def obj_to_template_str(obj):
    if len(obj) <= 0:
        return None

    out_arr = []
    for k, v in sorted(obj.items()):
        if isinstance(v, dict):
            obj_str = obj_to_template_str(v)
        elif isinstance(v, list):
            obj_str = arr_to_template_str(v)
        else:
            obj_str = None

        if obj_str is None:
            out_arr.append('"{}"'.format(k))
        else:
            out_arr.append('"{0}":{1}'.format(k, obj_str))

    return '{{{}}}'.format(','.join(out_arr))


def arr_to_template_str(arr):
    if len(arr) <= 0:
        return None

    out_arr = []
    for v in arr:
        if isinstance(v, dict):
            arr_str = obj_to_template_str(v)
        elif isinstance(v, list):
            arr_str = arr_to_template_str(v)
        else:
            arr_str = None

        if arr_str is None:
            out_arr.append('')
        else:
            out_arr.append('{}'.format(arr_str))

    return '[{}]'.format(','.join(out_arr))


def consume_next(char_list, char_set):
    while True:
        try:
            c = char_list.pop()
        except IndexError:
            raise IndexError('End of string reached unexpectedly')

        if c in char_set:
            return c
        elif not c.isspace():
            raise ValueError('Unexpected character `{}` encountered'.format(c))


def ws_trim(char_list):
    if char_list[-1].isspace():
        char_list.pop()


def prune_array_end(arr):
    if len(arr) < 2:
        return

    while True:
        if arr[-1] == arr[-2]:
            arr.pop()
            if len(arr) < 2:
                break
        else:
            break


def err_msg(msg, i, c):
    return '{0} @ index: {1}, character: {2}'.format(msg, i, c)


hex_re = compile('[0-9a-fA-F]')
json_encode = json.JSONEncoder(separators=(',', ':')).encode

if __name__ == "__main__":
    db = {
        'template': '[{"key_1"},]',
        'valid_records': [
            {
                'record_string': '[{"value_1"},3,{"key_2":"value_2"}]',
                'object': [{'key_1': 'value_1'}, 3, {'key_2': 'value_2'}]
            }
        ]
    }
    t = Template(db['template'])
    s = t.encode(db['valid_records'][0]['object'])
    print(t)
