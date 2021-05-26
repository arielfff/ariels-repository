###########################################################################################
# Asteroid State Object
#
# (c) Lutz Hamel, University of Rhode Island
###########################################################################################

from asteroid_symtab import SymTab

class State:
    def __init__(self):
        self.initialize()

    def initialize(self):
        self.symbol_table = SymTab()
        self.modules = [] # loaded modules
        self.AST = None
        self.ignore_quote = False # used to evaluate quoted expressions
        self.lineinfo = ("<input>", 1) # tuple: module, lineno

state = State()
