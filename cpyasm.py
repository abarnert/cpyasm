#!/usr/bin/env python3

"""Assembles CPython bytecode out of source in the dis module's format."""

import dis
import re
import types

class Assembler:
    
    _hasjrel = set(dis.hasjrel)
    _hasjabs = set(dis.hasjabs)
    _hasjump = _hasjrel | _hasjabs
    _hasconst = set(dis.hasconst)
    _hasfree = set(dis.hasfree)
    _hasname = set(dis.hasname)
    _haslocal = set(dis.haslocal)
    _hasnamed = _hasconst | _hasfree | _hasname | _haslocal
    _hascompare = set(dis.hascompare)
    
    def __init__(self, source=None,
                 constants=None, names=None, varnames=None, freevars=None,
                 filename=None, firstlineno=0, current_offset=0,
                 addnames=True):
        self.source = []
        self.filename = filename
        self._line = self.firstlineno = firstlineno
        self._offset = self.firstoffset = current_offset
        self._lnotab = []
        self._instructions = []
        self.constants = constants or [] # co_consts
        self.names = names or [] # co_names
        self.varnames = varnames or [] # co_varnames
        self.freevars = freevars or [] # co_freevars
        self._labels = {} # map label to instruction index
        self._jumptargets = set()
        if source:
            self.asm(source)

    def asm(self, source, addnames=True):
        for line in source.splitlines():
            self._addline(line, addnames)
            self.source.append(line)

    def __iter__(self):
        self._fixup()
        return iter(self._instructions)

    def dis(self):
        lineno_width = max(3, len(str(self._line)))
        return ''.join(instr._disassemble(lineno_width)+'\n' for instr in self)
    
    @property
    def codestring(self):
        self._fixup()
        def _encode(instr):
            if instr.opcode < dis.HAVE_ARGUMENT:
                return bytes((instr.opcode,))
            else:
                return bytes((instr.opcode, instr.arg, 0))
        return b''.join(map(_encode, self._instructions))

    @property
    def lnotab(self):
        b = bytearray()
        lastoffset, lastline = 0, 0
        for offset, line in self._lnotab:
            doffset = offset - lastoffset
            dline = line - lastline
            while doffset > 255:
                b.extend((255, 0))
                doffset -= 255
            while dline > 255:
                b.extend((0, 255))
                dline -= 255
            b.extend((doffset, dline))
            lastoffset, lastline = offset, line
        return bytes(b)
    
    def make_code(self, argcount, kwonlyargcount, nlocals, stacksize, flags,
                  name, cellvars=()):
        if self.firstoffset:
            raise ValueError('Cannot codify partial code objects')
        return types.CodeType(argcount, kwonlyargcount, nlocals,
                              stacksize, flags,
                              self.codestring,
                              tuple(self.constants), tuple(self.names),
                              tuple(self.varnames), self.filename, name,
                              self.firstlineno, self.lnotab,
                              tuple(self.freevars), cellvars)
    def make_function(self, argcount, kwonlyargcount, nlocals, stacksize, flags,
                      name, cellvars=(),
                      globals=None, fname=None, argdefs=None, closure=None,
                      _globals=globals):
        c = self.make_code(argcount, kwonlyargcount, nlocals, stacksize,
                           flags, name, cellvars)
        if globals is None:
            globals = _globals()
        return types.FunctionType(c, globals, fname, argdefs, closure)

    # Everything below here is private
    def _fixup(self):
        for i, instr in enumerate(self._instructions):
            if instr.opcode in self._hasjump:
                if isinstance(inst.arg, str):
                    try:
                        target = self._labels[instr.arg]
                    except LookupError:
                        # TODO: full SyntaxError
                        raise SyntaxError('Unassigned label {}'.format(inst.arg))
                    arg = argval = target.offset
                    if instr.opcode in self._hasjrel:
                        arg -= instr.offset + 3
                    argrepr = instr.argrepr
                    if not argrepr:
                        argrepr = 'to {} ({})'.format(instr.arg, argrepr)
                    self._instructions[i] = inst._replace(arg=arg,
                                                          argval=argval,
                                                          argrepr=argrepr)
                elif not instr.argval:
                    argval = instr.arg
                    if instr.opcode in dis.hasjrel:
                        argval += instr.offset + 3
                    argrepr = instr.argrepr
                    if not argrepr:
                        argrepr = 'to {}'.format(argval)
                    self._instructions[i] = inst._replace(argval=argval,
                                                          argrepr=argrepr)
                self._jumptargets.add(self._instructions[i].argval)
        for i in self._jumptargets:
            if not self._instructions[i].is_jump_target:
                instr = self._instructions[i]._replace(is_jump_target=True)
                self._instructions[i] = instr

    def _addblank(self):
        self._line += 1
        return len(self._instructions), self._offset, self._line
                    
    def _addlabel(self, name):
        self._labels[name] = len(self)
        self._line += 1
        return len(self._instructions), self._offset, self._line
                    
    def _addinstr(self, instr):
        if instr.is_jump_target:
            self._jumptargets.append(len(self._instructions))
        self._instructions.append(instr)
        self._lnotab.append((self._offset, self._line))
        self._offset += 1
        self._line += 1
        return len(self._instructions), self._offset, self._line
    
    def _addnoarg(self, opname, opcode, target):
        instr = dis.Instruction(opname, opcode, None, None, None,
                                self._offset, self._line, target)
        return self._addinstr(instr)

    def _addmisc(self, opname, opcode, arg, argrepr, target):
        if not argrepr:
            argrepr = arg
        try:
            arg = int(arg)
        except ValueError:
            raise SyntaxError("{} requires numeric arg, not {}".format(
                opname, arg))
        instr = dis.Instruction(opname, opcode, arg, arg, argrepr,
                                self._offset, self._line, target)
        return self._addinstr(instr)
    
    def _addjump(self, opname, opcode, arg, argrepr, target):
        # Nothing much to do here; see _fixup for the hard bit
        instr = dis.Instruction(opname, opcode, arg, argrepr, argrepr,
                                self._offset, self._line, target)
        return self._addinstr(instr)

    def _mapcompare(self, arg):
        try:
            return dis.cmp_op.index(arg), arg
        except ValueError:
            pass
        try:
            arg = int(arg)
            return arg, dis.cmp_op[arg]
        except (ValueError, LookupError):
            raise SyntaxError('{} is not a valid comparison operator'.format(arg))
    def _addcompare(self, opname, opcode, arg, argrepr, target):
        arg, argval = self._mapcompare(arg, argrepr)
        if not argrepr:
            argrepr = argval
        instr = dis.Instruction(opname, opcode, arg, argrepr, argrepr,
                                self._offset, self._line, target)
        return self._addinstr(instr)

    def _addnamed(self, opname, opcode, arg, argrepr, target, addnames):
        if opcode in self._hasconst:
            namelist = self.constants
        elif opcode in self._hasfree:
            namelist = self.freevars
        elif opcode in self._hasname:
            namelist = self.names
        elif opcode in self._haslocal:
            namelist = self.varnames
        try:
            arg = int(arg)
        except ValueError:
            pass
        else:
            try:
                argval = namelist[arg]
            except LookupError:
                # TODO: Warn about this?
                argval = '#{}'.format(arg)
            if not argrepr:
                argrepr = argval
            instr = dis.Instruction(opname, opcode, arg, argval, argrepr,
                                    self._offset, self._line, target)
            return self._addinstr(instr)
        argval = arg
        try:
            arg = namelist.index(argval)
        except ValueError:
            if addnames:
                arg = len(namelist)
                namelist.append(argval)
            else:
                raise SyntaxError("No such name '{}'".format(argval))
        if not argrepr:
            argrepr = argval
        instr = dis.Instruction(opname, opcode, arg, argval, argrepr,
                                self._offset, self._line, target)
        return self._addinstr(instr)        
    
    def _checknum(self, kind, inputval, curval):
        if inputval is None:
            return
        try:
            inputval = int(inputval)
        except ValueError:
            raise SyntaxError('{} {} is not an integer'.format(kind, inputval))
        if inputval != curval:
            raise SyntaxError('{} {} != {}'.format(kind, inputval, curval))
                
    def _addparts(self, line, target, offset, opname, arg, argrepr, addnames):
        try:
            opcode = dis.opmap[opname]
        except LookupError:
            # TODO: full SyntaxError, and search SyntaxError for all
            raise SyntaxError('No such opcode: {}'.format(opname))
        self._checknum('Line number', line, self._line)
        self._checknum('Offset', offset, self._offset)
        target = bool(target)
        if opcode < dis.HAVE_ARGUMENT:
            if arg is not None:
                raise SyntaxError('Opcode {} takes no argument'.format(opname))
            return self._addnoarg(opname, opcode, target)
        if arg is None:
            raise SyntaxError('Opcode {} requires an argument'.format(opname))
        if opcode in self._hasjump:
            return self._addjump(opname, opcode, arg, argrepr, target)
        elif opcode in self._hascompare:
            return self._addcompare(opname, opcode, arg, argrepr, target)
        elif opcode in self._hasnamed:
            return self._addnamed(opname, opcode, arg, argrepr, target,
                                  addnames)
        else:
            return self._addmisc(opname, opcode, arg, argrepr, target)

    # The output from dis is almost a regular language, except that
    # the first three columns are all optional, and the first and
    # third are identical formats, making it ambiguous. This regexp
    # will assign the value to the first column if only one exists,
    # which we'll have to fix up after the fact.
    _rline = re.compile(r'''(?x)
        \s*
        (?P<line>\d+(?=\s))? \s*
        (?P<target>>>)? \s*?
        (?P<offset>\d+)? \s*
        (?P<opname>[A-Za-z_]+) \s*
        (?P<arg>\S+)? \s*
        (?P<argrepr>\(.*?\))?''')
    _rlabel = re.compile(r'''\s*(?P<label>.*?)\s*:''')
    def _addline(self, line, addnames):
        if not line.strip():
            return self._addblank()
        m = self._rline.match(line)
        if not m:
            m = self._rlabel.match(line)
            if m:
                return self._addlabel(m.group('label'))
            # TODO: full SyntaxError
            raise SyntaxError('Cannot parse {}'.format(repr(line)))
        line, target, offset, opname, arg, argrepr = m.groups()
        if offset is None and line is not None:
            offset, line = line, offset
        return self._addparts(line, target, offset,
                              opname, arg, argrepr, addnames)

def test():
    a = Assembler('''
    LOAD_GLOBAL print
    LOAD_FAST a
    CALL_FUNCTION 1
    POP_TOP

    LOAD_GLOBAL print
    LOAD_GLOBAL f
    CALL_FUNCTION 1

    LOAD_CONST None
    RETURN_VALUE''', filename=__file__, firstlineno=329)

    global f
    f = a.make_function(1, 0, 1, 2, 0x43, 'f', argdefs=(0,))

    return a, f
    
if __name__ == '__main__':
    a, f = test()
    f('Hi')
