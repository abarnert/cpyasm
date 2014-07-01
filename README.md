cpyasm
======

A module for generating CPython bytecode from `dis`-like assembly

There are three basic uses for it: assembling individual lines,
assembling entire code objects, or reversing the output of the `dis`
module.

Simple example
==============

This example shows off most of the features of the module beyond the
obvious: auto-added names for globals and locals, labels, immediate
constant values, building code and function objects, and setting
file and line for inspection purposes.

    a = Assembler('''
    LOAD_GLOBAL print
    LOAD_FAST a
    CALL_FUNCTION 1
    POP_TOP
    JUMP_ABSOLUTE stupid

    stupid:
    LOAD_GLOBAL print
    LOAD_GLOBAL f
    CALL_FUNCTION 1
    JUMP_FORWARD stupider

    stupider:
    LOAD_CONST #None
    RETURN_VALUE''', filename='README.md', firstlineno=21)

    f = a.make_function(1, 0, 1, 2, 0x43, 'f', argdefs=(0,))
	f('Hi!')
	
This is equivalent to:

    def f(a=0):
	    print(a)
		print(f)
	f('Hi!')

Of course that `f` wouldn't have pointless jump statements in it; I
only added those to the assembly to show off labels working with both
relative and absolute addresses. But they don't change the effect of
the function; either version should do the same thing:

    Hi!
	<function README.f>

And if you call `dis.dis` or `inspect.getsource` or anything else on
it, you'll get exactly what you'd hope to get.

`class Assembler(source, addnames=True, *, **kwargs)`
=====================================================

An `Assembler` object assembles source code to `dis.Instruction`
objects, from which it can build bytecode, `code` objects, or
`function` objects.

Iterating over an `Assembler` object yields the `Instruction`s.

Normally, an `Assembler` is constructed from `source`; however, the
code can be left off if you'd prefer to add a piece at a time. (See
`asm` below.)

The `addnames` flag, if true, specifies that any unrecognized names or
values in the source will be added to the appropriate list (locals,
etc.), in the order they appear in the source. If false, any values
used in the code must be present in the pre-existing list. (Using
indexes instead of values makes this irrelevant.)

There are four optional arguments to pre-fill the lists; all but the
first are lists of strings. (You can pass any iterable, and
`Assembler` will copy it.)

* `constants`: Constants that the code references (`co_consts`). These
  can be any kind of Python value.
* `varnames`: Names of parameters and local variables that the code
  references (`co_varnames`).
* `freevars`: Free (closure/`nonlocal`) variables that the
  code references (`co_freevars`).
* `names`: Other names that the code references (`co_names`). This
  includes not only globals, but also other things like attribute
  names, and (if you're using ``LOAD_NAME` instead of `LOAD_GLOBAL` 
  and `LOAD_FAST`) even locals.

There are other arguments to assist in disassembling the assembled
code (which can be incorporated into `code` objects):

* `filename`: The path to the file the source code was compiled or
  assembled from, or some user-friendly string if no path.
* `firstlineno`: The line number, in the file, that the source code
  starts at.
* `current_offset`: The starting offset (within the enclosing code
  object) that the code starts at; useful for adding code to an
  existing object.

`Assembler` objects have the following attributes, methods, and
properties:

* `source`: The assembly source code given to the `Assembler`.

* `filename`: The filename passed to the constructor

* `constants`, `names`, `varnames`, `freevars`: The lists of values
  or names referenced by the code. You can use these to look up what
  `LOAD_FAST 0` means, or you can mutate them so you can assemble
  `LOAD_FAST 0` or `LOAD_FAST spam` and it will make sense.

* `asm(source, addnames=True)`: Assemble more source. You would
  generally do this if your use requires adding variable names and new
  code on the fly (e.g., assembling code out of an iterator, or even
  interactively).

* `dis()`: Returns a string with each `Instruction` objects
  disassembled, exactly the same way `dis.Bytecode.dis()` does.
  
* `codestring`: The actual assembled bytecode. Although this is built
  on the fly from the `Instruction`s, most errors in your code should
  have been caught at assembly time. The one major exception to that
  is using undefined labels. (Because labels can be used before
  they're defined, they have to be fixed up after the fact. To force
  labels to be checked and fixed up, you can always evaluate the
  `codestring`.)
  
* `lnotab`: The table of line numbers to offsets for the assembled
  bytecode. The format is documented in the Python source (under
  Objects/lnotab_notes.txt), but you shouldn't need this for anything
  other than passing it to a `code` object.  
  
* `make_code(argcount, kwonlyargcount, nlocals, stacksize, flags,
             name[, cellvars])`: Constructs a `code` object from
  the assembled bytecode. The arguments have the same meaning as
  in the `code` constructor (which is not very well documented; see
  the `inspect` module docs on the corresponding `co_foo` attributes
  for more information).
  
* `make_function(argcount, kwonlyargcount, nlocals, stacksize, flags,
                 name[, cellvars], 
				 globals=None, fname=None, argdefs=None,
                 closure=None)`:
  Constructs a `function` object, with corresponding `code` object,
  from the assembled bytecode. The arguments up to `cellvars` have
  the same meaning as in the `code` constructor; the last four
  arguments have the same meaning as in the `function` construction
  (except that `fname`, instead of `name`, is the argument to use if
  you for some reason want to give the `code` and `function` different
  names). As these constructors are not very well documented, see the
  `inspect` module docs on the corresponding `co_foo` and `__bar__`
  attributes for more information.
  
Assembly syntax
===============

Blank lines are always legal, and ignored.

Lines consisting of an identifier-like string followed by a colon
define a label; the label refers to the following (non-blank,
non-label) line of code, and can be used as an argument to jump
opcodes. (You can of course jump to labels defined later in the code.)

Everything else is parsed as a line of `dis` output, which looks like
this:

    337     >>   13 LOAD_GLOBAL              0 (print)

However, most of those columns are only useful for parsing the output
of `dis`; code you write yourself will probably only have at most two
columns:

    LOAD_CONST #None
	RETURN_VALUE
	
The columns are, respectively:

* **line number** (optional int). Normally, the `Assembler` will
  assign line numbers, starting from `firstlineno`, and going up 1
  line for each line of source (including blank lines), just as you'd
  expect. If you give it line numbers in the source code, this should
  allow you to override the automatic numbering, but that doesn't work
  yet; instead, you'll just confuse the assembler, causing it to print
  a warning for each line number and ignore it. (See TODO section.)
* **jump target flat** (optional, must be '>>' if present). If
  present, the line will be considered a jump target, even if nothing
  actually jumps there. (There's really no good reason you'd want
  that; it's primarily there to interpret `dis` output.)
* **offset** (optional int). Normally, the `Assembler` will assign
  offsets, starting from `current_offset` and going up by 1 or 3 for
  each instruction, as appropriate. If you give it offsets in the
  source code, this will confuse it, just like line numbers, and I'm
  not sure it should do differently. (See TODO section.)
* **opcode** (string). This must be one of the opcodes listed in the
  `dis` module documentation.
* **arg** (optional, int from 0-65535, or string, or literal prefixed 
  by `#`). If the opcode takes no arguments, this must not be
  present. Otherwise, it must be present. See Arguments below for the
  meaning of this field.
* **argrepr** (optional, string in parentheses). This cannot be
  present if the `arg` is not present. If it is, it overrides the
  usual representation of the `arg`. This only affects the
  disassembly output, not any code you assemble. It's quite possible
  to confuse yourself by, e.g., specifying `LOAD_FAST 0 (spam)` even
  though `varnames[0]` is actually `"eggs"`.
  
Arguments
=========

Different types of opcodes have different arguments, but there are
four basic forms:

* **Integer from 0-65535**: This is an index, address, offset, etc.,
  whatever is appropriate for the opcode.
* **Identifier**: This is the name of a global, local, or free
  variable, or a constant string, or a label, as appropriate for the
  opcode.
* **Operator symbol**: This is the normal Python symbol for a
  comparison operator, which is only appropriate for the `COMPARE_OP` 
  opcode.
* **# followed by a literal**: This is a constant value, which is only
  appropriate for the `LOAD_CONST` opcode.

If you aren't sure what arguments an opcode takes, look it up in the
`dis` module documentation. For example, `DUP_TOP` takes no arguments,
`CONTINUE_LOOP` takes a `target`, and `SET_ADD` takes an `i`.

Most of the argument types must be specified as an int, with the
following exceptions:

* `consti`: May be `#`-prefixed literal (which will be interpreted
  with `ast.literal_eval`) or an identifier (which means the
  identifier itself, as a string).
* `delta`: May be a label.
* `freei`: May be an identifier. Also, note that `LOAD_DEREF` and
  friends call their arguments `i` in the docs, but they're actually
  `freei`, so you can use an identifier with them. You can also do
  that with `LOAD_CLOSURE` if you're sure that `co_cellvars` will end
  up empty, but if not, it will do the wrong thing.
* `namei`: May be an identifier.
* `opname`: May be an operator symbol, like `==`.
* `target`: May be a label.
* `var_num`: May be an identifier.

You can also look up the opcode as `dis.opmap[opcode]`, in which case:

* `< dis.HAVE_ARGUMENT` (90, as of 3.4.1): no arguments
* `in dis.hasconst`: `consti`, allows literal or identifier
* `in dis.hasfree`: `freei`, allows identifier
* `in dis.hasname`: `namei`, allows identifier
* `in dis.haslocal`: `var_num`, allows identifier
* `in dis.hasjrel`: `delta`, allows label
* `in dis.hasjabs`: `target`, allows label
* `in dis.hascompare`: `opname`, allows operator symbol
* `else`: must be an int

When you specify an identifier or a constant literal, it's looked up
in the appropriate list and converted to an index; if `addnames` is
true, it's added first if not present. The code does not actually
check the Python identifier rules, so if you want to call a local
variable `2cool4grammar`, you can, and it will work, but you may
confuse debuggers and the like.

When you specify a label, the label may not yet exist. In that case,
the `Instruction` will have the label itself as its argument (which is
obviously not valid). When you generate bytecode, all labels are fixed
up (which also fixes any missing jump target flags).

In some cases, the single int is treated as two numbers, the high and
low bytes of the int, which you can extract as `i >> 8` and `i &
0xFF`, or combine as `(hi << 8) | lo`. It would be nice if you could
specify the pair of numbers here instead of combining them yourself,
but at present you can't.

TODO
====

Comments! I think the Python-style "everything from `#` to the end of
the line is ignored" rule seems obvious, except that I already used
`#` to mean "immediate constant literal", so one or the other has to
give.

There may need to be two different modes for line numbers. If you want
to line-number the assembly code, you ignore any line numbers in the
source and let it automatically number lines of assembly; if you want
the line numbers to correspond to something else (like some Python
code you've compiled, disassembled, hacked up, and want to
reassemble), you tell it not to automatically number anything, and go
by lines embedded in the source.

Offsets are a bigger issue. It might make sense to allow skipping
offsets (filling the gaps with `NOP`), but going backward can't do
anything useful. So the only things you'd want to do are check that
the offsets are valid, or ignore them. (The former would make sense
when you'd munged some disassembly and want to ensure that you haven't
broken any jump ops, etc.)

When assembling anything bigger than a function, like a whole module,
each function has its own offsets starting from 0. In that case, each
function starts with `Disassembly of <name>:`, which we could
interpret as a special kind of label that lets us know we've got
another function. The question is, what could you usefully do with
that? Unless we're going to add code to build module objects, .pyc
files, etc., not much. But if we do nothing, we can't actually reverse
everything `dis.dis` does--which may be fine, it just needs to be
documented.

It might be worth trying to keep track of `cellvars`. Of course you'd
still need to specify the actual cells to make a function, but we
could at least check that the lists match up. This would mean we'd
need fixup code on every `LOAD_CLOSURE` that uses a name, because
`cellvars` and `freevars` may have changed since it was
assembled. But, more seriously, how would you specify whether an
unrecognized name in `LOAD_CLOSURE` was a cell or a free variable?

I'm not sure I've got the cell and free variables stuff right anyway;
it's been a while since I hacked around at the internals of
closures. So, `LOAD_DEREF` and friends could already be broken, I
could have made no sense in the previous paragraph, etc.

There are other arguments we could simplify. In particular, it's a bit
annoying to write `CALL_FUNCTION 258` instead of something like
`CALL_FUNCTION 2,1`.

It might be nice to handle extended args automatically; if you write
an opcode with an int > 65535 (maybe you need to flag it to verify
that it's not a mistake?) it emits `EXTENDED_ARG` and then your opcode
(meaning your 1 line now took 6 bytes, instead of the usual 1 or
3... but that's not a problem as long as we document the
possibility). But I think that's only ever used for `MAKE_FUNCTION`,
so maybe a better idea would be to allow `MAKE_FUNCTION 1,2,4` and
turn that into `EXTENDED_ARG 4` and `MAKE_FUNCTION 258`?

It might even be nice to add some higher-level stuff, basically to
allow `CALL_FUNCTION` to take names as args. But that would require
some way to mark them each as global, local, const, or free. We've
already got `#` for const, maybe default to global (because usually at
least the function name will be global), add `^` for local and `&` for
free, so:

    CALL_FUNCTION print,^a,#'end'=#''
	
... becomes:

    LOAD_GLOBAL print
	LOAD_FAST a
	LOAD_CONST #'end'
	LOAD_CONST #''
	CALL_FUNCTION 1,1
	
And likewise, maybe:

    LOAD_ATTR ^self.spam
	
... becomes:

    LOAD_FAST self
	LOAD_ATTR spam

... and so on.
	
But before going that far, probably better to look at what people
demand first from real assemblers (bearing in mind that a lot of it is
unnecessary with Python's higher-level bytecode, but a lot of it
may not be).
