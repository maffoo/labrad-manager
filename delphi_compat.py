#!/usr/bin/python

import labrad
import labrad.types as T 
import labrad.units
import datetime
import re

# 
# Utility functions needed to be compatible with the delphi labrad implementation
#
# The first part are data_to_string and string_to_data functions used by the
# registry server and the manager utility functions of the same name
#
# The second part implements unit and type conversion that attempts to be compatible
# with the delphi manager.
#

def data_to_string(data):
    # Types with non-trivial units.  Dimensionless numbers handled same as float/complex
    if isinstance(data, T.Value) and not data.isDimensionless():
        return str(data)
    if isinstance(data, T.Complex) and not data.isDimensionless():
        return '%s %s' % (data_to_string(data.value), data.unit)
    # Other scalar types
    if isinstance(data, str):
        data = data.replace("'", "''")
        output = ''
        quoted = False
        for x in data:
            if ord(x) < 32 or ord(x) > 126:
                if quoted:
                    output += "'"
                    quoted=False
                output += '#%d'%ord(x)
            else:
                if not quoted:
                    output += "'"
                    quoted = True
                output += x
        if quoted:
            output += "'"
        return output
    if isinstance(data, (bool, float)):
        return repr(data)
    if isinstance(data, long):
        return repr(int(data))
    if isinstance(data, int):
        return "%+d" % data
    if isinstance(data, complex):
        if data.imag >= 0:
            return '%s+%si' % (repr(data.real), repr(data.imag))
        else:
            return '%s%si' % (repr(data.real), repr(data.imag))
    if data is None:
        return '_'

    # Composite types
    if isinstance(data, tuple):
        return '(' + ','.join([ data_to_string(d) for d in data ]) + ')'
    if isinstance(data, list):
        return '[' + ','.join([ data_to_string(d) for d in data ]) + ']'
    if isinstance(data, datetime.datetime): # Format: 10/30/2013 16:15:28.844409738667309
        return data.strftime('%m/%d/%Y %H:%M:%S.%f')


        
# If first non-white character is [, (. or ': list, tuple, or string
# if first character is digit: word
# if first non-white character is +/-: numeric types
#     If contains internal space: Value/Complex
#     If contains i: complex
#     If contains .: float
#     else int
# If first non-white character is alphabetic: bool

date_re = re.compile(r'\d+/\d+/\d+ \d+:\d+:\d+(\.\d+)?')
long_re = re.compile('\d+')
int_re = re.compile('[+-]\d+')
string_re = re.compile("('[^'\000-\037\177-\377]*'|#[0-9]{1,3})+")
float_re = re.compile(r'(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|NAN\.0)')
complex_re = re.compile(r'%s\+?%s[ij]' % (float_re.pattern, float_re.pattern))
unit_re = re.compile(r'[A-Za-z][A-Za-z0-9^/*]*')
value_re = re.compile(r'(%s) (%s)' % (float_re.pattern, unit_re.pattern))
complex_value_re = re.compile(r'(%s) (%s)' % (complex_re.pattern, unit_re.pattern))
true_re = re.compile(r'[Tt]rue')
false_re = re.compile(r'[Ff]alse')
none_re = re.compile(r'_')

# List of match functions.  The first match will be used, so put things with
# units first.

def string_to_data(s):
    try:
        result = decode_string(s)[0]
        return result
    except Exception as e:
        print "Unable to decode string '%s'" % (s,)
        raise

def decode_string(s):
    if s[0] in '[(':
        match_fun = list if s[0]=='[' else tuple
        match_chr = ']' if s[0]=='[' else ')'
        l= []
        rest = s[1:]
        if rest[0] == match_chr:
            return match_fun(l), rest[1:]
        while True:
            (item, rest) = decode_string(rest)
            l.append(item)
            if rest[0] == match_chr:
                return match_fun(l), rest[1:]
            if rest[0] == ',':
                rest = rest[1:]
            else:
                raise RuntimeError('Illegal data string "%s"' % (s,))
    else:
        for pattern, func in token_types:
            mo = pattern.match(s)
            if mo:
                return func(mo.group()), s[mo.end():]
        raise RuntimeError('Illegal data string "%s"' % (s,))
    
def parse_string(in_str):
    string_element_re = "'[^'\000-\037\177-\377]*'|#[0-9]{1,3}"
    matches = re.findall(string_element_re, in_str)
    result = ''
    last_was_string = False
    for m in matches:
        if m[0] == "'":
            if last_was_string:
                result += m[:-1] # leave one quote in
            else:
                result += m[1:-1]
            last_was_string=True
        else:
            result += chr(int(m[1:]))
            last_was_string=False
    return result
        
def parse_complex(in_str):
    return complex(in_str[:-1]+'j')
def parse_value(in_str):
    mo = value_re.match(in_str)
    if mo.group(1) == "NAN.0":
        x = float('nan')
    else:
        x = float(mo.group(1))
    return x*labrad.units.Unit(mo.group(2))
def parse_complex_value(in_str):
    mo = complex_value_re.match(in_str)
    return parse_complex(mo.group(1)) * labrad.units.Unit(mo.group(2))
    
def parse_number(in_str):
    if '.' in in_str or 'e' in in_str or 'E' in in_str:
        if in_str == 'NAN.0':
            return float('nan')
        return float(in_str)
    elif in_str[0] in "+-":
        return int(in_str)
    else:
        return long(in_str)

def parse_date(in_str):
    idx = in_str.rfind('.')
    if idx >= 0:
        dt = datetime.timedelta(float(in_str[idx:]))
        time = datetime.datetime.strptime(in_str[:idx], '%m/%d/%Y %H:%M:%S')
        return time+dt
    else:
        time = datetime.datetime.strptime(in_str, '%m/%d/%Y %H:%M:%S')
        return time

token_types = [(value_re, parse_value),
          (complex_value_re, parse_complex_value),
          (date_re, parse_date),
          (complex_re, parse_complex),
          (float_re, parse_number),
          (string_re, parse_string),
          (true_re, lambda x: True),
          (false_re, lambda x: False),
          (none_re, lambda x: None)]


def convert_units(data, allowed_types):
    '''
    Convert a data object to one of the allowed labrad typetags.
    We first check to see if any of the candidates are acceptable, and we find out
    whether the the match is exact or whether we need to do unit conversions.
    '''
    if not allowed_types:
        if data:
            print "No types found, but non-zero data. "
        return data, T.getType(data)
    objtype = T.parseTypeTag(T.getType(data))
    for candidate in allowed_types:
        compatible, output_type = check_types(objtype, T.parseTypeTag(candidate))
        #print "compat: %s, output_type: %s" % ( compatible, output_type)
        if compatible == 0:
            continue
        if compatible == 2:
            return data, output_type
        if compatible == 1:
            return do_conversion(data, output_type), output_type
    raise RuntimeError("Unable to convert %s to any allowed type (%s)" % (data, allowed_types))

def check_types(objtype, candidate_type):
    '''
    Returns 0 if object is incompatible with the candiate
    Returns 1 if the object is compatible but requires type conversion
    Returns 2 if the object matches the candidate type and is more specific (no conversion needed)
    '''
    if isinstance(candidate_type, T.LRAny):
        return 2, objtype

    # integer types are compatible with each other
    if isinstance(objtype, (T.LRInt, T.LRWord)) and isinstance(candidate_type, (T.LRInt, T.LRWord)) :
        return (1 + (type(candidate_type) == type(objtype))), candidate_type

    # These types are only compatible with themselves and never need conversion
    if isinstance(objtype, (T.LRStr, T.LRBool, T.LRTime, T.LRNone)):
        return 2*(type(candidate_type) == type(objtype)), candidate_type

    # Error is compatible with another error iff the payload is compatible
    if isinstance(objtype, T.LRError) and isinstance(candidate_type, T.LRError):
        compatibility, payload_type = check_types(objtype.payload, candidate_type.payload)
        return compatibility, T.LRError(payload_type)

    if isinstance(objtype, T.LRComplex) and not isinstance(candidate_type, T.LRComplex):
        # Can't convert complex to real
        return 0, candidate_type
    if isinstance(objtype, T.LRComplex) and isinstance(candidate_type, T.LRComplex):
        # both complex
        compat, unit = compatible_units(objtype.unit, candidate_type.unit)
        return compat, T.LRComplex(unit)
    if isinstance(objtype, T.LRValue) and isinstance(objtype, T.LRComplex):
        # Conver real to complex
        _, unit = compatible_units(objtype.unit, candidate_type.unit)
        return 1, T.LRComplex(unit)
        
    if isinstance(objtype, T.LRValue) and isinstance(candidate_type, T.LRValue):
        # Both real
        compat, unit = compatible_units(objtype.unit, candidate_type.unit)
        return compat, T.LRValue(unit)

    if isinstance(objtype, T.LRCluster) and isinstance(candidate_type, T.LRCluster):
        if len(objtype.items) != len(candidate_type.items):
            return 0, candidate_type
        result = []
        for t1,t2 in zip(objtype.items, candidate_type.items):
            result.append(check_types(t1, t2))
        compat = min([x[0] for x in result])
        typetag = T.LRCluster(*tuple([x[1] for x in result]))
        return compat, typetag
    if isinstance(objtype, T.LRList) and isinstance(candidate_type, T.LRList):
        if objtype.depth != candidate_type.depth:
            return 0, candidate_type
        if isinstance(objtype.elem, T.LRNone): # Empty arrays match anything
            return 2, candidate_type
        compat, elem = check_types(objtype.elem, candidate_type.elem)
        return compat, T.LRList(elem, depth=candidate_type.depth)
    return 0, candidate_type

def compatible_units(u_input, u_target):
    '''
    Figure out if the input can be converted to the target untis,
    according to the old labrad manager rules
    '''
    if u_input is None and u_target is None:
        return 2, None
    if u_input is None:
        return 1, u_target
    if u_target is None:
        return 2, u_input
    u_input = labrad.units.Unit(u_input)
    u_target = labrad.units.Unit(u_target)
    if u_input.conversionFactorTo(u_target)==1.0:
        return 2, u_target
    if u_input.isCompatible(u_target):
        return 1, u_target
    return 0, u_target

def do_conversion(data, typetag):
    '''
    Convert the data to the specified type tag, converting units
    '''
    if isinstance(typetag, T.LRBool):
        return bool(data)
    if isinstance(typetag, T.LRInt):
        return int(data)
    if isinstance(typetag, T.LRWord):
        return long(data)
    if isinstance(typetag, T.LRStr):
        return str(data)
    if isinstance(typetag, T.LRNone):
        return data
    if isinstance(typetag, T.LRTime):
        return data
    if isinstance(typetag, T.LRComplex):
        if isinstance(data, (labrad.units.Complex, labrad.units.Value)):
            return (data+0j).inUnitsOf(typetag.unit)
        else:
            return labrad.units.Complex(data+0j, typetag.unit)
    if isinstance(typetag, T.LRValue):
        if isinstance(data, (labrad.units.Value, labrad.units.Complex)):
            return data.inUnitsOf(typetag.unit)
        else:
            return labrad.units.Value(data, typetag.unit)
    if isinstance(typetag, T.LRCluster):
        result = []
        for x in zip(data, typetag.items):
            result.append(do_conversion(*x))
        return tuple(result)
    if isinstance(typetag, T.LRList):
        if isinstance(data, T.LazyList) and isinstance(typetag.elem, (T.LRValue, T.LRComplex)):
            array_data = data.asarray
            input_unit = labrad.units.Unit(data.elem.unit)
            output_unit = labrad.units.Unit(typetag.elem.unit)
            if input_unit and output_unit:
                return input_unit.conversionFactorTo(output_unit) * array_data
            elif output_unit:
                return array_data
            else:
                return array_data
        result = []
        for x in data:
            if typetag.depth==1:
                result.append(do_conversion(x, typetag.elem))
            else:
                result.append(do_conversion(x, T.LRList(typetag.elem, typetag.depth-1)))
        return result
    if isinstance(typetag, T.LRError):
        return data
