#########################################################################
# A tree walker to interpret Asteroid programs
#
# (c) Lutz Hamel, University of Rhode Island
#########################################################################

from asteroid_globals import *
from asteroid_support import *
from copy import deepcopy
from asteroid_state import state
from re import match as re_match

#########################################################################
# this dictionary maps list member function names to function
# implementations given in the Asteroid prologue.
# see 'prologue.ast' for details
list_member_functions = dict()

#########################################################################
# this dictionary maps string member function names to function
# implementations given in the Asteroid prologue.
# see 'prologue.ast' for details
string_member_functions = dict()

#########################################################################
__retval__ = None  # return value register for escaped code

###########################################################################################
# check if the two type tags match
def match(tag1, tag2):

    if tag1 == tag2:
        return True
    else:
        return False

###########################################################################################
def unify(term, pattern, unifying = True ):
    '''
    unify term and pattern recursively and return the unifier.
    this unification allows for the same variable to appear
    multiple times in the unifier.  the user of this
    function must take appropriate actions if this happens.

    we assume that both the term and the pattern are made up of tuple
    nodes:

             (<type>, children*)

    leaf nodes must be nullary constructors.

    NOTE: if the pattern looks like an lval then it is treated like an lval, e.g.
            let a@[0] = 'a@[0].
          stores the term 'a@[0] into lval a@[0].
    NOTE: Default argument unifying is set to be true. If we are unifying, then we are
          evaluating unification between a pattern and a term. If we are not
          unifying, then we are evaluating subsumption between two patterns for the
          purpose of detecting redundant/useless pattern clauses in functions.
    '''
    #lhh
    # print("unifying:\nterm: {}\npattern: {}\n\n".format(term, pattern))

    # if unifying:
    #     print("unifying:\nterm: {}\npattern: {}\n\n".format(term, pattern))
    # else:
    #     print("evaluating subsumption:\nterm: {}\npattern: {}\n\n".format(term, pattern))

    # 1. We don't care what the pattern is called if evaluating subsumption.
    # 2. A named patterns node(tuple) shape can get us into trouble when unpacking. This intial
    # check allows us to unpack it normally as opposed to checking each time we unpack.
    try:
        if ((not unifying) and (term[0] == 'named-pattern')):
            term = term[2]
    except:
        pass

    ### Python value level matching
    # NOTE: in the first rules where we test instances we are comparing
    # Python level values, if they don't match exactly then we have
    # a pattern match fail.
    if isinstance(term, str): # apply regular expression match
        if isinstance(pattern, str) and re_match("^"+pattern+"$", term):
            # Note: a pattern needs to match the whole term.
            return [] # return empty unifier
        else:
            raise PatternMatchFailed(
                "regular expression {} did not match {}"
                .format(pattern, term))

    elif isinstance(term, (int, float, bool)):
        if term == pattern:
            return [] # return an empty unifier
        else:
            raise PatternMatchFailed(
                "{} is not the same as {}"
                .format(term, pattern))

    elif isinstance(term, list) or isinstance(pattern, list):
        if not(isinstance(term, list)) or not(isinstance(pattern, list)):
            raise PatternMatchFailed(
                "term and pattern do not agree on list/tuple constructor")
        elif len(term) != len(pattern):
            raise PatternMatchFailed(
                "term and pattern lists/tuples are not the same length")
        else:
            unifier = []
            for i in range(len(term)):
                if unifying:
                    unifier += unify(term[i], pattern[i])
                else:
                    unifier += unify(term[i], pattern[i], False)
            return unifier

    ### Asteroid value level matching
    elif pattern[0] == 'string' and term[0] != 'string':
        # regular expression applied to a non-string structure
        # this is possible because all data types are subtypes of string
        return unify(term2string(term), pattern[1])

    elif pattern[0] == 'cmatch':

        if not unifying:

            ### Condtional Pattern Subsumption
            # The current behavior for Asteroid when encoutering a conditional pattern when
            # evaluating subsumption is to throw a warning.

            print("Warning: Condtional patterns not supported for redundancy analysis.")
            print("\t Redundant or useless pattern clauses may exist in function definition(s).")
            pass

        (CMATCH, pexp, cond_exp) = pattern

        if unifying:
            unifiers = unify(term, pexp)
        else:
            unifiers = unify(term, pexp, False)

        # evaluate the conditional expression in the
        # context of the unifiers.
        #state.symbol_table.push_scope({})
        declare_unifiers(unifiers)
        bool_val = map2boolean(walk(cond_exp))
        #state.symbol_table.pop_scope()
        if bool_val[1]:
            return unifiers
        else:
            raise PatternMatchFailed(
                "conditional pattern match failed")

    elif pattern[0] == 'typematch':
        typematch = pattern[1]
        nextIndex = 0 #indicates index of where we will 'look' next

        if typematch in ['string','real','integer','list','tuple','boolean','none']:

            if (not unifying):

                #walk a different path for this node
                if (term[0] == 'typematch'):
                    nextIndex = 1

                #handle lists/head-tails subsuming each other
                elif (term[0] in ['list','head-tail']):
                    if ((typematch == 'list') and (term[0] in ['list','head-tail'])):
                        return []

            if typematch == term[nextIndex]:
                return []
            else:
                raise PatternMatchFailed(
                    "expected typematch {} got a term of type {}"
                    .format(typematch, term[nextIndex]))

        elif typematch == 'function':
            # matching function and member function values
            if term[0] in ['function-val','member-function-val']:
                return []
            else:
                raise PatternMatchFailed(
                    "expected typematch {} got a term of type {}"
                    .format(typematch, term[0]))

        elif term[0] == 'object':
            (OBJECT,
                (STRUCT_ID, (ID, struct_id)),
                (OBJECT_MEMORY, LIST)) = term
            if struct_id == typematch:
                    return []
            else:
                raise PatternMatchFailed(
                    "expected typematch {} got an object of type {}"
                    .format(typematch, struct_id))

        # ttc
        # Should we have an else here?

    elif pattern[0] == 'named-pattern':
        # unpack pattern
        (NAMED_PATTERN, name, p) = pattern

        if unifying:
            return unify(term, p ) + [(name, term )]
        else:
            return unify(term, p, False)

    elif pattern[0] == 'none':
        if term[0] != 'none':
            raise PatternMatchFailed("expected 'none' got '{}'"
                    .format(term[0]))
        else:
            return []

    # NOTE: functions/foreign are allowed in terms as long as they are matched
    # by a variable in the pattern - anything else will fail
    elif term[0] in (unify_not_allowed - {'function-val', 'foreign'}):
        raise PatternMatchFailed(
            "term of type '{}' not allowed in pattern matching"
            .format(term[0]))

    elif pattern[0] in unify_not_allowed:
        raise PatternMatchFailed(
            "pattern of type '{}' not allowed in pattern matching"
            .format(pattern[0]))

    elif pattern[0] == 'quote':
        # quotes on the pattern side can always be ignored
        if unifying:
            return unify(term, pattern[1])
        else:
            return unify(term, pattern[1], False)

    elif term[0] == 'quote' and pattern[0] not in ['id', 'index']:
        # ignore quote on the term if we are not trying to unify term with
        # a variable or other kind of lval
        if unifying:
            return unify(term[1], pattern)
        else:
            return unify(term, pattern[1], False)

    elif term[0] == 'object' and pattern[0] == 'apply':
        # unpack term
        (OBJECT,
         (STRUCT_ID, (ID, struct_id)),
         (OBJECT_MEMORY, (LIST, obj_memory))) = term
        # unpack pattern
        (APPLY,
         (ID, apply_id),
         arg) = pattern
        if struct_id != apply_id:
            raise PatternMatchFailed("expected type '{}' got type '{}'"
                .format(apply_id, struct_id))
        # we are comparing raw lists here
        if arg[0] == 'tuple':
            pattern_list = arg[1]
        else:
            pattern_list = [arg]
        # only pattern match on object data members
        if unifying:
            return unify(data_only(obj_memory), pattern_list)
        else:
            return unify(data_only(obj_memory), pattern_list, False)

    elif pattern[0] == 'index': # list element lval access
        unifier = (pattern, term)
        return [unifier]

    elif term[0] == 'id' and unifying: # variable in term not allowed
        raise PatternMatchFailed(      # when unifying
            "variable '{}' in term not allowed"
            .format(term[1]))

    elif pattern[0] == 'id': # variable in pattern add to unifier
        sym = pattern[1]
        if sym == '_': # anonymous variable - ignore unifier
            return []
        else:
            unifier = (pattern, term)
            return [unifier]

    elif pattern[0] in ['head-tail', 'raw-head-tail']:

        # if we are unifying or we are not evaluating subsumption
        #  to another head-tail
        if unifying or term[0] not in ['head-tail', 'raw-head-tail']:
            (HEAD_TAIL, pattern_head, pattern_tail) = pattern
            (LIST, list_val) = term

            if LIST != 'list':
                raise PatternMatchFailed(
                    "head-tail operator expected type 'list' got type '{}'"
                    .format(LIST))

            if not len(list_val):
                raise PatternMatchFailed(
                    "head-tail operator expected a non-empty list")

            list_head = list_val[0]
            list_tail = ('list', list_val[1:])

            unifier = []
            if unifying:
                unifier += unify(list_head, pattern_head)
                unifier += unify(list_tail, pattern_tail)
            else:
                unifier += unify(list_head, pattern_head,False)
                unifier += unify(list_tail, pattern_tail,False)
            return unifier

        else: #Else we are evaluating subsumption to another head-tail

            lengthH = head_tail_length(pattern) #H->higher order of predcence pattern
            lengthL = head_tail_length(term)    #L->lower order of predcence pattern

            if lengthH == 2 and lengthL != 2:
                return unify(pattern[1],term[1],False)

            if (lengthH > lengthL): # If the length of the higher presedence pattern is greater
                                    # then length of the lower precedence pattern, it is
                                    # not redundant
                raise PatternMatchFailed(
                    "Subsumption relatioship broken, pattern will not be rendered redundant.")

            else: #Else we continue evaluating the different terms in the head-tail pattern
                (HEAD_TAIL, patternH_head, patternH_tail) = pattern
                (HEAD_TAIL, patternL_head, patternL_tail) = term
                return unify(patternL_head,patternH_head,False) + unify(patternL_tail,patternH_tail,False)

    elif pattern[0] == 'deref':  # ('deref', ('id', sym))
        (ID, sym) = pattern[1]
        p = state.symbol_table.lookup_sym(sym)
        if unifying:
            return unify(term,p)
        else:
            return unify(term,p, False)

    # builtin operators look like apply lists with operator names
    elif pattern[0] == 'apply':
        if term[0] != pattern[0]: # make sure both are applys
            raise PatternMatchFailed(
                "term and pattern disagree on 'apply' node")

        # unpack the apply structures
        (APPLY, (ID, t_id), t_arg) = term
        (APPLY, (ID, p_id), p_arg) = pattern

        # make sure apply id's match
        if t_id != p_id:
            raise PatternMatchFailed(
                "term '{}' does not match pattern '{}'"
                .format(t_id, p_id))

        # unify the args
        if unifying:
            return unify(t_arg, p_arg)
        else:
            return unify(t_arg, p_arg,False)

    elif not match(term[0], pattern[0]):  # nodes are not the same
        raise PatternMatchFailed(
            "nodes '{}' and '{}' are not the same"
            .format(term[0], pattern[0]))

    elif len(term) != len(pattern): # nodes are not of same the arity
        raise PatternMatchFailed(
            "nodes '{}' and '{}'' are not of the same arity"
            .format(term[0], pattern[0]))

    else:
        #lhh
        #print("unifying {}".format(pattern[0]))
        unifier = []
        for i in range(1,len(term)):
            if unifying:
                unifier += unify(term[i], pattern[i])
            else:
                unifier += unify(term[i], pattern[i], False)
        #lhh
        #print("returning unifier: {}".format(unifier))
        return unifier

#########################################################################
def eval_actual_args(args):

    return walk(args)

#########################################################################
def declare_formal_args(unifiers):
    # unfiers is of the format: [ (pattern, term), (pattern, term),...]

    for u in unifiers:
        (pattern, term) = u
        (ID, sym) = pattern
        if ID != 'id':
            raise ValueError("no pattern match possible in function call")
        state.symbol_table.enter_sym(sym, term)

#########################################################################
# we are indexing into the memory of either a list/tuple/string or an
# object to read the memory.
#
# NOTE: when indexed with a scalar it will return a single value,
# that value of course could be a list etc.  When index with a list
# then it will return a list of values. Therefore:
#       a@1 =/= a@[1]
# the value on the left of the inequality is a single value, the
# value on the right is a singleton list.
def read_at_ix(structure_val, ix):

    # find the actual memory we need to access
    # list: return the actual list
    if structure_val[0] in ['list', 'tuple', 'string']:
        if structure_val[0] == 'list' \
        and ix[0] == 'id' \
        and ix[1] in list_member_functions:
            # we are looking at the function name of a list member
            # function - find the implementation and return it.
            impl_name = list_member_functions[ix[1]]
            # remember the object reference.
            return ('member-function-val',
                    structure_val,
                    state.symbol_table.lookup_sym(impl_name))
        elif structure_val[0] == 'string' \
        and ix[0] == 'id' \
        and ix[1] in string_member_functions:
            # we are looking at the function name of a string member
            # function - find the implementation and return it.
            impl_name = string_member_functions[ix[1]]
            # remember the object reference.
            return ('member-function-val',
                    structure_val,
                    state.symbol_table.lookup_sym(impl_name))
        else:
            # get a reference to the memory
            memory = structure_val[1]
            # compute the index
            ix_val = walk(ix)

    # for objects we access the object memory
    elif structure_val[0] == 'object':
        (OBJECT,
         (STRUCT_ID, (ID, struct_id)),
         (OBJECT_MEMORY, (LIST, memory))) = structure_val
        # compute the index -- for objects this has to be done
        # in the context of the struct scope
        struct_val = state.symbol_table.lookup_sym(struct_id)
        # unpack the struct value
        (STRUCT,
         (MEMBER_NAMES, (LIST, member_names)),
         (STRUCT_MEMORY, (LIST, struct_memory)),
         (STRUCT_SCOPE, struct_scope)) = struct_val
        state.symbol_table.push_scope(struct_scope)
        ix_val = walk(ix)
        state.symbol_table.pop_scope()

    else:
        raise ValueError("'{}' is not indexable".format(structure_val[0]))

    # index into memory and get value(s)
    if ix_val[0] == 'integer':
        if structure_val[0] == 'string':
            return ('string', memory[ix_val[1]])
        elif structure_val[0] == 'object' \
        and memory[ix_val[1]][0] == 'function-val':
            # remember the object reference.
            return ('member-function-val',
                    structure_val,
                    memory[ix_val[1]])
        else:
            return memory[ix_val[1]]

    elif ix_val[0] == 'list':
        if len(ix_val[1]) == 0:
            raise ValueError("index list is empty")

        return_memory = []
        for i in ix_val[1]:
            (IX_EXP_TYPE, ix_exp) = i

            if IX_EXP_TYPE == 'integer':
                return_memory.append(memory[ix_exp])
            else:
                raise ValueError("unsupported list index")

        if structure_val[0] == 'string':
            return ('string',"".join(return_memory))
        else:
            return ('list', return_memory)

    else:
        raise ValueError("index op '{}' not supported".format(ix_val[0]))

#########################################################################
# we are indexing into the memory of either a list or an object to
# write into the memory.
def store_at_ix(structure_val, ix, value):

    # find the actual memory we need to access
    # for lists it is just the python list
    if structure_val[0] == 'list':
        memory = structure_val[1]
        # compute the index
        ix_val = walk(ix)

    # for objects we access the object memory
    elif structure_val[0] == 'object':
        (OBJECT,
         (STRUCT_ID, (ID, struct_id)),
         (OBJECT_MEMORY, (LIST, memory))) = structure_val
        # compute the index -- for objects this has to be done
        # in the context of the struct scope
        struct_val = state.symbol_table.lookup_sym(struct_id)
        # unpack the struct value
        (STRUCT,
         (MEMBER_NAMES, (LIST, member_names)),
         (STRUCT_MEMORY, (LIST, struct_memory)),
         (STRUCT_SCOPE, struct_scope)) = struct_val
        state.symbol_table.push_scope(struct_scope)
        ix_val = walk(ix)
        state.symbol_table.pop_scope()

    else:
        raise ValueError("'{}' is not mutable a structure".format(structure_val[0]))


    # index into memory and set the value
    if ix_val[0] == 'integer':
        memory[ix_val[1]] = value
        return

    elif ix_val[0] == 'list':
        raise ValueError("slicing in patterns not supported")

    else:
        raise ValueError("index op '{}' in patterns not supported"
                         .format(ix_val[0]))

#########################################################################
def handle_builtins(node):

    (APPLY, (ID, opname), args) = node
    assert_match(APPLY, 'apply')
    assert_match(ID, 'id')

    if opname in binary_operators:
        (TUPLE, bin_args)= args
        val_a = walk(bin_args[0])
        val_b = walk(bin_args[1])

        if opname == '__plus__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real', 'list', 'boolean']:
                return (type, val_a[1] + val_b[1])
            elif type == 'string':
                return (type, term2string(val_a) + term2string(val_b))
            else:
                raise ValueError('unsupported type {} in +'.format(type))
        elif opname == '__minus__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real']:
                return (type, val_a[1] - val_b[1])
            else:
                raise ValueError('unsupported type {} in -'.format(type))
        elif opname == '__times__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real']:
                return (type, val_a[1] * val_b[1])
            else:
                raise ValueError('unsupported type in *')
        elif opname == '__divide__':
            type = promote(val_a[0], val_b[0])
            if type == 'integer':
                return (type, int(val_a[1]) // int(val_b[1]))
            elif type == 'real':
                return ('real', float(val_a[1]) / float(val_b[1]))
            else:
                raise ValueError('unsupported type in /')
        elif opname == '__or__':
            # NOTE: do we need to typecheck here?
            if map2boolean(val_a)[1] == True or map2boolean(val_b)[1] == True:
               return ('boolean', True)
            else:
               return ('boolean', False)
        elif opname == '__and__':
            # NOTE: do we need to typecheck here?
            if map2boolean(val_a)[1] == True and map2boolean(val_b)[1] == True:
               return ('boolean', True)
            else:
               return ('boolean', False)
        elif opname == '__eq__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real', 'list', 'string', 'boolean']:
                return ('boolean', val_a[1] == val_b[1])
            else:
                raise ValueError('unsupported type in ==')
        elif opname  == '__ne__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real', 'list', 'string', 'boolean']:
                return ('boolean', val_a[1] != val_b[1])
            else:
                raise ValueError('unsupported type in =/=')
        elif opname == '__le__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real']:
                return ('boolean', val_a[1] <= val_b[1])
            else:
                raise ValueError('unsupported type in <=')
        elif opname == '__lt__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real']:
                return ('boolean', val_a[1] < val_b[1])
            else:
                raise ValueError('unsupported type in <')
        elif opname == '__ge__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real']:
                return ('boolean', val_a[1] >= val_b[1])
            else:
                raise ValueError('unsupported type in >=')
        elif opname == '__gt__':
            type = promote(val_a[0], val_b[0])
            if type in ['integer', 'real']:
                return ('boolean', val_a[1] > val_b[1])
            else:
                raise ValueError('unsupported type in >')
        else:
            raise ValueError('unknown builtin binary opname {}'.format(opname))

    elif opname in unary_operators:
        arg_val = walk(args)

        if opname == '__not__':
            val = map2boolean(arg_val)
            if val[1] == False:
                return ('boolean', True)
            elif val[1] == True:
                return ('boolean', False)
            else:
                raise ValueError('not a boolean value in not')
        elif opname == '__uminus__':
            if arg_val[0] in ['integer', 'real']:
                return (arg_val[0], - arg_val[1])
            else:
                raise ValueError(
                    'unsupported type {} in unary minus'
                    .format(arg_val[0]))
        else:
            raise ValueError('unknown builtin unary opname {}'.format(opname))

#########################################################################
def handle_call(fval, actual_val_args):

    (FUNCTION_VAL, body_list, closure) = fval
    assert_match(FUNCTION_VAL, 'function-val')

    # static scoping for functions
    # Note: we have to do this here because unifying
    # over the body patterns can introduce variable declarations,
    # think conditional pattern matching.
    save_symtab = state.symbol_table.get_config()
    state.symbol_table.set_config(closure)
    state.symbol_table.push_scope({})

    #lhh
    #print('in handle_call')
    #print("calling: {}\nwith: {}\n\n".format(fval,actual_val_args))

    # iterate over the bodies to find one that unifies with the actual parameters
    (BODY_LIST, (LIST, body_list_val)) = body_list
    unified = False

    for body in body_list_val:

        (BODY,
         (PATTERN, p),
         (STMT_LIST, stmts)) = body

        try:
            unifiers = unify(actual_val_args, p)
            unified = True
        except PatternMatchFailed:
            unifiers = []
            unified = False

        if unified:
            break

    if not unified:
        raise ValueError("none of the function bodies unified with actual parameters")

    declare_formal_args(unifiers)

    # execute the function
    # function calls transfer control - save our caller's lineinfo
    old_lineinfo = state.lineinfo

    try:
        walk(stmts)
    except ReturnValue as val:
        return_value = val.value
    else:
        return_value = ('none', None) # need that in case function has no return statement

    # coming back from a function call - restore caller's lineinfo
    state.lineinfo = old_lineinfo

    # NOTE: popping the function scope is not necessary because we
    # are restoring the original symtab configuration. this is necessary
    # because a return statement might come out of a nested with statement
    state.symbol_table.set_config(save_symtab)

    return return_value

#########################################################################
def declare_unifiers(unifiers):
    # walk the unifiers and bind name-value pairs into the symtab

    # TODO: check for repeated names in the unfiers

    for unifier in unifiers:

        #lhh
        #print("unifier: {}".format(unifier))

        (lval, value) = unifier

        if lval[0] == 'id':
            state.symbol_table.enter_sym(lval[1], value)

        elif lval[0] == 'index': # list/structure lval access
            # Note: structures have to be declared before index access
            # can be successful!!  They have to be declared so that there
            # is memory associated with the structure.

            (INDEX, structure, ix) = lval
            # look at the semantics of 'structure'
            structure_val = walk(structure)
            # indexing/slicing
            # update the memory of the object.
            store_at_ix(structure_val, ix, value)

        else:
            raise ValueError("unknown unifier type '{}'".format(lval[0]))

#########################################################################
# node functions
#########################################################################
def global_stmt(node):

    (GLOBAL, (LIST, id_list)) = node
    assert_match(GLOBAL, 'global')
    assert_match(LIST, 'list')

    for id_tuple in id_list:
        (ID, id_val) = id_tuple
        if state.symbol_table.is_symbol_local(id_val):
            raise ValueError("{} is already local, cannot be declared global"
                             .format(id_val))
        state.symbol_table.enter_global(id_val)

#########################################################################
def assert_stmt(node):

    (ASSERT, exp) = node
    assert_match(ASSERT, 'assert')

    exp_val = walk(exp)
    # mapping asteroid assert into python assert
    assert exp_val[1], 'assert failed'

#########################################################################
def unify_stmt(node):

    (UNIFY, pattern, exp) = node
    assert_match(UNIFY, 'unify')

    term = walk(exp)
    unifiers = unify(term, pattern)
    declare_unifiers(unifiers)

#########################################################################
def return_stmt(node):

    (RETURN, e) = node
    assert_match(RETURN, 'return')

    raise ReturnValue(walk(e))

#########################################################################
def break_stmt(node):

    (BREAK,) = node
    assert_match(BREAK, 'break')

    raise Break()

#########################################################################
def throw_stmt(node):

    (THROW, object) = node
    assert_match(THROW, 'throw')

    raise ThrowValue(walk(object))

#########################################################################
def try_stmt(node):

    (TRY,
     (STMT_LIST, try_stmts),
     (CATCH_LIST, (LIST, catch_list))) = node

    try:
        walk(try_stmts)

    # NOTE: in Python the 'as inst' variable is only local to the catch block???
    except ThrowValue as inst:
        except_val = inst.value
        inst_val = inst

    except ReturnValue as inst:
        # return values should never be captured by user level try stmts - rethrow
        raise inst

    except PatternMatchFailed as inst:
        # convert a Python string to an Asteroid string
        except_val = ('tuple',
                      [('string', 'PatternMatchFailed'), ('string', inst.value)])
        inst_val = inst

    except Exception as inst:
        # convert exception args to an Asteroid string
        except_val = ('tuple',
                      [('string', 'Exception'), ('string', str(inst))])
        inst_val = inst

    else:
        # no exceptions found in the try statements
        return

    # we had an exception - walk the catch list and find an appropriate set of
    # catch statements.
    for catch_val in catch_list:
        (CATCH,
         (CATCH_PATTERN, catch_pattern),
         (CATCH_STMTS, catch_stmts)) = catch_val
        try:
            unifiers = unify(except_val, catch_pattern)
        except PatternMatchFailed:
            pass
        else:
            declare_unifiers(unifiers)
            walk(catch_stmts)
            return

    # no exception handler found - rethrow the exception
    raise inst_val

#########################################################################
def loop_stmt(node):

    (LOOP, body_stmts) = node
    assert_match(LOOP, 'loop')

    (STMT_LIST, body) = body_stmts

    try:
        while True:
            walk(body)
    except Break:
        pass

#########################################################################
def while_stmt(node):

    (WHILE, cond_exp, body_stmts) = node
    assert_match(WHILE, 'while')

    (COND_EXP, cond) = cond_exp
    (STMT_LIST, body) = body_stmts

    try:
        (COND_TYPE, cond_val) = map2boolean(walk(cond))
        while cond_val:
            walk(body)
            (COND_TYPE, cond_val) = map2boolean(walk(cond))
    except Break:
        pass

#########################################################################
def repeat_stmt(node):

    (REPEAT, body_stmts, cond_exp) = node
    assert_match(REPEAT, 'repeat')

    (COND_EXP, cond) = cond_exp
    (STMT_LIST, body) = body_stmts

    try:
        while True:
            walk(body)
            (COND_TYPE, cond_val) = map2boolean(walk(cond))
            if cond_val:
                break

    except Break:
        pass

#########################################################################
def for_stmt(node):

    (FOR, (IN_EXP, in_exp), (STMT_LIST, stmt_list)) = node
    assert_match(FOR, 'for')

    (IN, pattern, list_term) = in_exp

    # expand the list_term
    (LIST_TYPE, list_val) = walk(list_term)
    if LIST_TYPE not in ['list','string']:
        raise ValueError("only iteration over strings and lists is supported")

    # we allow iteration over two types of structures: (1) lists (2) strings
    # if it is a string turn the list_val into a list of Asteroid characters.
    if LIST_TYPE == 'string':
        new_list = []
        for c in list_val:
            new_list.append(('string',c))
        list_val = new_list

    # for each term on the list unfiy with pattern, declare the bound variables,
    # and execute the loop body in that context
    # NOTE: just like Python, loop bodies do not create a new scope!
    # NOTE: we can use unification as a filter of elements:
    #
    #      for (2,y) in [(1,11), (1,12), (1,13), (2,21), (2,22), (2,23)]  do
    #             print y.
    #      end for
    try:
        for term in list_val:
            try:
                unifiers = unify(term,pattern)
            except PatternMatchFailed:
                pass
            else:
                declare_unifiers(unifiers)
                walk(stmt_list)
    except Break:
        pass

#########################################################################
def if_stmt(node):

    (IF, (LIST, if_list)) = node
    assert_match(IF, 'if')
    assert_match(LIST, 'list')

    for if_clause in if_list:

        (IF_CLAUSE,
         (COND, cond),
         (STMT_LIST, stmts)) = if_clause

        (BOOLEAN, cond_val) = map2boolean(walk(cond))

        if cond_val:
            walk(stmts)
            break

#########################################################################
def struct_def_stmt(node):

    (STRUCT_DEF, (ID, struct_id), (MEMBER_LIST, (LIST, member_list))) = node
    assert_match(STRUCT_DEF, 'struct-def')
    assert_match(ID, 'id')
    assert_match(MEMBER_LIST, 'member-list')
    assert_match(LIST, 'list')

    # declare members
    # member names are declared as variables whose value is the slot
    # in a struct object
    struct_memory = [] # this will serve as a template for instanciating objects
    member_names = []
    struct_scope = {}
    state.symbol_table.push_scope(struct_scope)

    for member_ix in range(len(member_list)):
        member = member_list[member_ix]
        if member[0] == 'data':
            (DATA, (ID, member_id)) = member
            state.symbol_table.enter_sym(member_id, ('integer', member_ix))
            struct_memory.append(('none', None))
            member_names.append(member_id)
        elif member[0] == 'unify':
            (UNIFY, (ID, member_id), function_exp) = member
            state.symbol_table.enter_sym(member_id, ('integer', member_ix))
            # Note: we have to bind a function VALUE into the structure memory
            function_val = walk(function_exp)
            struct_memory.append(function_val)
            member_names.append(member_id)
        elif member[0] == 'noop':
            pass
        else:
            raise ValueError("unsupported struct member '{}'".format(member[0]))

    state.symbol_table.pop_scope()

    struct_type = ('struct',
                  ('member-names', ('list', member_names)),
                  ('struct-memory', ('list', struct_memory)),
                  ('struct-scope', struct_scope))

    state.symbol_table.enter_sym(struct_id, struct_type)

#########################################################################
def eval_exp(node):

    (EVAL, exp) = node
    assert_match(EVAL, 'eval')
    # lhh
    #print("in eval with {}".format(node))

    # Note: eval is essentially a macro call - that is a function
    # call without pushing a symbol table record.  That means
    # we have to first evaluate the argument to 'eval' before
    # walking the term.  This is safe because if the arg is already
    # the actual term it will be quoted and nothing happens if it is
    # a variable it will be expanded to the actual term.
    #lhh
    #print("before expand: {}".format(exp))
    exp_val_expand = walk(exp)
    #lhh
    #print("after expand: {}".format(exp_val_expand))
    # now walk the actual term
    state.ignore_quote = True
    exp_val = walk(exp_val_expand)
    #lhh
    #print("after walk: {}".format(exp_val))
    state.ignore_quote = False
    return exp_val

#########################################################################
def apply_exp(node):

    (APPLY, f, arg) = node
    assert_match(APPLY, 'apply')

    # handle builtin operators that look like apply lists.
    if f[0] == 'id' and f[1] in operator_symbols:
        return handle_builtins(node)

    # handle function application
    f_val = walk(f)
    arg_val = walk(arg)

    # object member function
    # NOTE: object member functions are passed an object reference.
    if f_val[0] == 'member-function-val':
        (MEMBER_FUNCTION_VAL, obj_ref, function_val) = f_val
        # Note: lists and tuples are objects/mutable data structures, they
        # have member functions defined in the Asteroid prologue.
        if arg_val[0] == 'none':
            result = handle_call(function_val, obj_ref)
        elif arg_val[0] != 'tuple':
            new_arg_val = ('tuple', [obj_ref, arg_val])
            result = handle_call(function_val, new_arg_val)
        elif arg_val[0] == 'tuple':
            arg_val[1].insert(0, obj_ref)
            result = handle_call(function_val, arg_val)
        else:
            raise ValueError(
                "unknown parameter type '{}' in apply"
                .format(arg_val[0]))

    # regular function call
    elif f_val[0] == 'function-val':
        result = handle_call(f_val, arg_val)

    # object constructor call
    elif f_val[0] == 'struct':
        (ID, struct_id) = f
        (STRUCT,
         (MEMBER_NAMES, (LIST, member_names)),
         (STRUCT_MEMORY, (LIST, struct_memory)),
         (STRUCT_SCOPE, struct_scope)) = f_val

        # create our object memory - memory cells now have initial values
        # TODO: why is this not shared among objects?
        object_memory = struct_memory.copy()
        # create our object
        obj_ref = ('object',
                  ('struct-id', ('id', struct_id)),
                  ('object-memory', ('list', object_memory)))
        # if the struct has an __init__ function call it on the object
        # NOTE: constructor functions do not have return values.
        if '__init__' in member_names:
            slot_ix = member_names.index('__init__')
            init_fval = struct_memory[slot_ix]
            # calling a member function - push struct scope
            state.symbol_table.push_scope(struct_scope)
            if arg_val[0] == 'none':
                handle_call(init_fval, obj_ref)
            elif arg_val[0] != 'tuple':
                arg_val = ('tuple', [obj_ref, arg_val])
                handle_call(init_fval, arg_val)
            elif arg_val[0] == 'tuple':
                arg_val[1].insert(0, obj_ref)
                handle_call(init_fval, arg_val)
            state.symbol_table.pop_scope()
        # the struct does not have an __init__ function but
        # we have a constructor call with args, e.g. Foo(1,2)
        # try to apply a default constructor by copying the
        # values from the arg list to the data slots of the object
        elif arg_val[0] != 'none':
            if arg_val[0] != 'tuple':
                arg_array = [arg_val]
            else:
                arg_array = arg_val[1]
            data_memory = data_only(object_memory)
            if len(data_memory) != len(arg_array):
                raise ValueError(
                    "default constructor expected {} arguments got {}"
                    .format(len(data_memory), len(arg_array)))
            # copy initializers into object memory
            data_ix = data_ix_list(object_memory)
            for (i,k) in zip(data_ix, range(0,len(data_memory))):
                object_memory[i] = arg_array[k]

        # return the new object
        result = obj_ref

    else:
        raise ValueError("unknown apply term '{}'".format(f_val[0]))

    return result

#########################################################################
def index_exp(node):

    (INDEX, structure, ix) = node
    assert_match(INDEX, 'index')

    # look at the semantics of 'structure'
    structure_val = walk(structure)

    # indexing/slicing
    result = read_at_ix(structure_val, ix)
    #lhh
    #from pprint import pprint
    #pprint(structure_val)

    return result

#########################################################################
def list_exp(node):

    (LIST, inlist) = node
    assert_match(LIST, 'list')

    outlist =[]

    for e in inlist:
        outlist.append(walk(e))

    return ('list', outlist)

#########################################################################
def tuple_exp(node):

    (TUPLE, intuple) = node
    assert_match(TUPLE, 'tuple')

    outtuple = []

    for e in intuple:
        outtuple.append(walk(e))

    return ('tuple', outtuple)

#########################################################################
def escape_exp(node):

    (ESCAPE, s) = node
    assert_match(ESCAPE, 'escape')

    global __retval__
    __retval__ = ('none', None)

    exec(s)

    return __retval__

#########################################################################
def is_exp(node):

    (IS, term, pattern) = node
    assert_match(IS, 'is')

    term_val = walk(term)

    try:
        unifiers = unify(term_val, pattern)
    except PatternMatchFailed:
        return ('boolean', False)
    else:
        declare_unifiers(unifiers)
        return ('boolean', True)

#########################################################################
def in_exp(node):

    (IN, exp, exp_list) = node
    assert_match(IN, 'in')

    exp_val = walk(exp)
    (EXP_LIST_TYPE, exp_list_val, *_) = walk(exp_list)

    if EXP_LIST_TYPE != 'list':
        raise ValueError("right argument to in operator has to be a list")

    # we simply map our in operator to the Python in operator
    if exp_val in exp_list_val:
        return ('boolean', True)
    else:
        return ('boolean', False)

#########################################################################
def if_exp(node):

    (IF_EXP, cond_exp, then_exp, else_exp) = node
    assert_match(IF_EXP, 'if-exp')

    (BOOLEAN, cond_val) = map2boolean(walk(cond_exp))

    if cond_val:
        return walk(then_exp)
    else:
        return walk(else_exp)

#########################################################################
# NOTE: 'to-list' is not a semantic value and should never appear in
#       any tests.  It is a constructor and should be expanded by the
#       walk function before semantic processing.
def to_list_exp(node):

    (TOLIST,
     (START, start),
     (STOP, stop),
     (STEP, step)) = node

    assert_match(TOLIST, 'to-list')
    assert_match(START, 'start')
    assert_match(STOP, 'stop')
    assert_match(STEP, 'step')

    (START_TYPE, start_val, *_) = walk(start)
    (STOP_TYPE, stop_val, *_) = walk(stop)
    (STEP_TYPE, step_val, *_) = walk(step)

    if START_TYPE != 'integer' or STOP_TYPE != 'integer' or STEP_TYPE != 'integer':
        raise ValueError("only integer values allowed in start, stop, or step")

    out_list_val = []

    # TODO: check out the behavior with step -1 -- is this what we want?
    # the behavior is start and stop included
    if int(step_val) > 0: # generate the list
        ix = int(start_val)
        while ix <= int(stop_val):
            out_list_val.append(('integer', ix))
            ix += int(step_val)

    elif int(step_val) == 0: # error
        raise ValueError("step size of 0 not supported")

    elif int(step_val) < 0: # generate the list
        ix = int(start_val)
        while ix >= int(stop_val):
            out_list_val.append(('integer', ix))
            ix += int(step_val)

    else:
        raise ValueError("{} not a valid step value".format(step_val))

    return ('list', out_list_val)

#########################################################################
# NOTE: this is the value view of the head tail constructor, for the
#       pattern view of this constructor see unify.
def head_tail_exp(node):

    (HEAD_TAIL, head, tail) = node
    assert_match(HEAD_TAIL, 'head-tail')

    head_val = walk(head)
    (TAIL_TYPE, tail_val) = walk(tail)

    if TAIL_TYPE != 'list':
        raise ValueError(
            "unsuported tail type {} in head-tail operator".
            format(TAIL_TYPE))

    return ('list', [head_val] + tail_val)

#########################################################################
# turn a function expression into a closure.
def function_exp(node):

    (FUNCTION_EXP, body_list) = node
    assert_match(FUNCTION_EXP,'function-exp')

    return ('function-val',
            body_list,
            state.symbol_table.get_config())

#########################################################################
# Named patterns - when walking a named pattern we are interpreting a
# a pattern as a constructor - ignore the name
def named_pattern_exp(node):

    (NAMED_PATTERN, name, pattern) = node
    assert_match(NAMED_PATTERN,'named-pattern')

    return walk(pattern)

#########################################################################
def process_lineinfo(node):

    (LINEINFO, lineinfo_val) = node
    assert_match(LINEINFO, 'lineinfo')

    #lhh
    #print("lineinfo: {}".format(lineinfo_val))

    state.lineinfo = lineinfo_val

#########################################################################
def typematch_exp(node):

    (TYPEMATCH, type) = node
    assert_match(TYPEMATCH, 'typematch')

    raise ValueError(
            "typematch {} cannot appear in expressions or constructors"
            .format(type))

#########################################################################
def cmatch_exp(node):

    (CMATCH, exp, cond_exp) = node
    assert_match(CMATCH, 'cmatch')

    # on a walk to interpret the tree as a value we simply
    # ignore the conditional expression
    return walk(exp)

#########################################################################
def deref_exp(node):

    (DEREF, id_exp) = node
    assert_match(DEREF, 'deref')

    # deref operators are only meaningful during pattern matching
    # ignore during a value walk.
    # NOTE: the second walk is necessary to interpret what we retrieved
    # through the indirection
    return walk(walk(id_exp))

#########################################################################
# walk
#########################################################################
def walk(node):
    # node format: (TYPE, [child1[, child2[, ...]]])
    type = node[0]

    if type in dispatch_dict:
        node_function = dispatch_dict[type]
        return node_function(node)
    else:
        raise ValueError("feature {} not yet implemented".format(type))

# a dictionary to associate tree nodes with node functions
dispatch_dict = {
    # statements - statements do not produce return values
    'lineinfo'      : process_lineinfo,
    'noop'          : lambda node : None,
    'assert'        : assert_stmt,
    'unify'         : unify_stmt,
    'while'         : while_stmt,
    'loop'          : loop_stmt,
    'repeat'        : repeat_stmt,
    'for'           : for_stmt,
    'global'        : global_stmt,
    'return'        : return_stmt,
    'break'         : break_stmt,
    'if'            : if_stmt,
    'throw'         : throw_stmt,
    'try'           : try_stmt,
    'struct-def'    : struct_def_stmt,
    # expressions - expressions do produce return values
    'list'          : list_exp,
    'tuple'         : tuple_exp,
    'to-list'       : to_list_exp,
    'head-tail'     : head_tail_exp,
    'raw-to-list'   : lambda node : walk(('to-list', node[1], node[2], node[3])),
    'raw-head-tail' : lambda node : walk(('head-tail', node[1], node[2])),
    'seq'           : lambda node : ('seq', walk(node[1]), walk(node[2])),
    'none'          : lambda node : node,
    'nil'           : lambda node : node,
    'function-exp'  : function_exp,
    'string'        : lambda node : node,
    'integer'       : lambda node : node,
    'real'          : lambda node : node,
    'boolean'       : lambda node : node,
    'eval'          : eval_exp,
    # quoted code should be treated like a constant if not ignore_quote
    'quote'         : lambda node : walk(node[1]) if state.ignore_quote else node,
    # type tag used in conjunction with escaped code in order to store
    # foreign objects in Asteroid data structures
    'foreign'       : lambda node : node,
    'id'            : lambda node : state.symbol_table.lookup_sym(node[1]),
    'apply'         : apply_exp,
    'index'         : index_exp,
    'escape'        : escape_exp,
    'is'            : is_exp,
    'in'            : in_exp,
    'if-exp'        : if_exp,
    'named-pattern' : named_pattern_exp,
    'member-function-val' : lambda node : node,
    'typematch'     : typematch_exp,
    'cmatch'        : cmatch_exp,
    'deref'         : deref_exp,
}
