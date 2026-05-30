from __future__ import annotations

from typing import List, Optional

from ..RunTime import Body, Module
from .AST.ASE import (
    AssignStmtNode,
    BlockNode,
    BreakStmtNode,
    CompoundAssignStmtNode,
    ClassDefNode,
    ContinueStmtNode,
    DeleteStmtNode,
    DerefAssignStmtNode,
    ExprStmtNode,
    ForCStmtNode,
    ForRangeStmtNode,
    FunctionDefNode,
    IfStmtNode,
    ReturnNode,
    ScopedAssignStmtNode,
    ScopedCompoundAssignStmtNode,
    ScopedVarDeclNode,
    SwitchStmtNode,
    TemplateFunctionDefNode,
    VarDeclNode,
    VarScopeOrderStmtNode,
    WhileStmtNode,
    StructDefNode,
    ThrowStmtNode,
    TryStmtNode,
    ImportStmtNode,
    FromImportStmtNode,
    NamespaceDefNode,
)
from .AST.Data import (
    ArrayLiteralNode,
    AttributeAccessNode,
    BinOpNode,
    BinOperator,
    FunctionCallNode,
    IndexAccessNode,
    IndexStoreNode,
    LiteralsNode,
    BoolLiteralNode,
    ScopedLoadNode,
    UnaryOpNode,
    UnaryOperator,
    VariableLoadNode,
)
from .Lexer import Lexer, Token
from .preprocessor import PreprocessorError, preprocess


class ParseError(SyntaxError):
    pass


_COMPOUND_ASSIGN_OPS = {
    "PLUSEQ": BinOperator.add,
    "MINEQ": BinOperator.sub,
    "STAREQ": BinOperator.mul,
    "SLASHEQ": BinOperator.div,
    "PERCENTEQ": BinOperator.mod,
    "CARETEQ": BinOperator.bitxor,
    "AMPEQ": BinOperator.bitand,
    "PIPEEQ": BinOperator.bitor,
    "LSHIFTEQ": BinOperator.shl,
    "RSHIFTEQ": BinOperator.shr,
}
_COMPOUND_ASSIGN_TYPES = frozenset(_COMPOUND_ASSIGN_OPS)


class Parser:
    def __init__(self, tokens: List[Token], source: str = ""):
        self.tokens = tokens
        self.p = 0
        self.source = source

    @classmethod
    def parse_source(cls, text: str, filename: str | None = None) -> Module:
        try:
            expanded = preprocess(text, filename)
        except PreprocessorError as e:
            raise ParseError(str(e)) from e
        toks = Lexer(expanded).tokenize()
        mod = cls(toks, expanded).parse_module(filename)
        from ..TypeCheck import StaticTypeError, check_module_static_types

        try:
            check_module_static_types(mod)
        except StaticTypeError as e:
            raise ParseError(str(e)) from e
        return mod

    def cur(self) -> Token:
        return self.tokens[self.p]

    def peek(self, k: int = 1) -> Token:
        j = self.p + k
        return self.tokens[j] if j < len(self.tokens) else self.tokens[-1]

    def eat(self, *expect: str) -> Token:
        t = self.cur()
        if expect and t.type not in expect:
            raise ParseError(f"expected {expect}, got {t.type} ({t.value!r}) at {t.line}:{t.col}")
        self.p += 1
        return t

    def _next_after_balanced_paren(self, lp_index: int) -> Token:
        depth = 0
        i = lp_index
        while i < len(self.tokens):
            tt = self.tokens[i].type
            if tt == "LPAREN":
                depth += 1
            elif tt == "RPAREN":
                depth -= 1
                if depth == 0:
                    nxt = i + 1
                    if nxt < len(self.tokens):
                        return self.tokens[nxt]
                    return self.tokens[-1]
            i += 1
        raise ParseError("unbalanced parentheses")

    def parse_module(self, filename: str | None = None) -> Module:
        stmts: list = []
        while self.cur().type != "EOF":
            if self.cur().type == "SEMI":
                self.eat("SEMI")
                continue
            stmts.append(self.parse_stmt())
        lines = self.source.splitlines() if self.source else []
        from ..RunTime import Frame, StackFrame

        glob: dict = {}
        builtins_ns = {}
        try:
            from ...PyModules.builtin_namespace import builtin_namespace

            builtins_ns = dict(builtin_namespace)
        except ImportError:
            pass
        body = Body(stmts)
        fr = Frame(
            f_body=body,
            f_globals=glob,
            f_locals=glob,
            f_builtins=builtins_ns,
        )
        mod = Module(body, lines, file=filename)
        body.sf = StackFrame(fr, "<module>", mod)
        return mod

    def parse_stmt(self):
        t = self.cur().type
        if t == "STATIC":
            self.eat("STATIC")
            if self.cur().type not in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "IDENT"):
                raise ParseError("static 后必须是变量类型声明")
            if self.cur().type == "IDENT":
                typ = self.eat("IDENT").value
                typ = self._consume_type_ptr_ref_suffix(typ)
                if self.cur().type == "IDENT" and self.peek().type == "LPAREN":
                    after = self._next_after_balanced_paren(self.p + 1)
                    if after.type == "LBRACE":
                        raise ParseError("static 不支持函数定义")
                return self.parse_var_decl_rest(typ, is_static=True)
            return self.parse_type_start_stmt(is_static=True)
        if t == "IMPORT":
            return self.parse_import_stmt()
        if t == "FROM":
            return self.parse_from_import_stmt()
        if t == "EXPORT":
            self.eat("EXPORT")
            st = self.parse_stmt()
            if hasattr(st, "name"):
                setattr(st, "_is_export", True)
                return st
            raise ParseError("export 仅可修饰具名定义（变量/函数/类/结构体）")
        if t == "CONST":
            self.eat("CONST")
            if self.cur().type not in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "IDENT"):
                raise ParseError("const 后必须是变量类型声明")
            if self.cur().type == "IDENT":
                typ = self.eat("IDENT").value
                typ = self._consume_type_ptr_ref_suffix(typ)
                if self.cur().type == "IDENT" and self.peek().type == "LPAREN":
                    after = self._next_after_balanced_paren(self.p + 1)
                    if after.type == "LBRACE":
                        raise ParseError("const 不支持函数定义；请使用 constexpr")
                return self.parse_var_decl_rest(typ, is_const=True)
            return self.parse_type_start_stmt(is_const=True)
        if t == "CONSTEXPR":
            self.eat("CONSTEXPR")
            if self.cur().type not in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "VOID", "IDENT"):
                raise ParseError("constexpr 后必须是类型声明或函数声明")
            if self.cur().type == "IDENT":
                typ = self.eat("IDENT").value
                typ = self._consume_type_ptr_ref_suffix(typ)
                if self.cur().type == "IDENT" and self.peek().type == "LPAREN":
                    after = self._next_after_balanced_paren(self.p + 1)
                    if after.type == "LBRACE":
                        return self.parse_function_def(typ, (), is_constexpr=True)
                return self.parse_var_decl_rest(typ, is_constexpr=True)
            return self.parse_type_start_stmt(is_constexpr=True)
        if t == "STAR":
            save = self.p
            self.eat("STAR")
            lhs = self.parse_unary()
            if self.cur().type == "EQ":
                self.eat("EQ")
                rhs = self.parse_expr()
                self.eat("SEMI")
                return DerefAssignStmtNode(lhs, rhs)
            self.p = save
        if t == "IF":
            return self.parse_if_stmt()
        if t == "WHILE":
            return self.parse_while_stmt()
        if t == "FOR":
            return self.parse_for_stmt()
        if t == "SWITCH":
            return self.parse_switch_stmt()
        if t == "TEMPLATE":
            return self.parse_template_function()
        if t == "NAMESPACE":
            return self.parse_namespace()
        if t == "CLASS":
            return self.parse_class()
        if t == "STRUCT":
            return self.parse_struct()
        if t == "RETURN":
            self.eat("RETURN")
            if self.cur().type == "SEMI":
                self.eat("SEMI")
                return ReturnNode(None)
            e = self.parse_expr()
            self.eat("SEMI")
            return ReturnNode(e)
        if t == "BREAK":
            self.eat("BREAK")
            self.eat("SEMI")
            return BreakStmtNode()
        if t == "CONTINUE":
            self.eat("CONTINUE")
            self.eat("SEMI")
            return ContinueStmtNode()
        if t == "THROW":
            self.eat("THROW")
            ex = None
            if self.cur().type != "SEMI":
                ex = self.parse_expr()
            self.eat("SEMI")
            return ThrowStmtNode(ex)
        if t == "TRY":
            return self.parse_try_stmt()
        if t == "DELETE":
            self.eat("DELETE")
            names = [self.eat("IDENT").value]
            while self.cur().type == "COMMA":
                self.eat("COMMA")
                names.append(self.eat("IDENT").value)
            self.eat("SEMI")
            return DeleteStmtNode(names)
        if t == "VARSCOPEORDER":
            self.eat("VARSCOPEORDER")
            entries: list = []
            while True:
                n = self.eat("IDENT").value
                self.eat("COLON")
                if self.cur().type == "LPAREN":
                    self.eat("LPAREN")
                    order = [self.parse_scope_spec_raw()]
                    while self.cur().type == "ARROW":
                        self.eat("ARROW")
                        order.append(self.parse_scope_spec_raw())
                    self.eat("RPAREN")
                    entries.append((n, tuple(order)))
                else:
                    entries.append((n, self.parse_scope_spec_raw()))
                if self.cur().type != "COMMA":
                    break
                self.eat("COMMA")
            self.eat("SEMI")
            return VarScopeOrderStmtNode(entries)
        if t == "LBRACE":
            return self.parse_block_stmt()
        if t in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "VOID"):
            return self.parse_type_start_stmt()
        if t in ("GLOBAL", "LOCAL", "BUILTINS", "CLOSURE"):
            return self.parse_scoped_assign_or_decl()
        if t == "THIS":
            self.eat("THIS")
            ex = self._parse_postfix_continue(VariableLoadNode("this"))
            return self._finish_expr_stmt_from_lhs(ex)
        if t == "BASE":
            self.eat("BASE")
            ex = self._parse_postfix_continue(VariableLoadNode("base"))
            return self._finish_expr_stmt_from_lhs(ex)
        if t == "IDENT":
            if self.peek().type == "NEW" and self.peek(2).type == "LT":
                typ = self.eat("IDENT").value
                typ = self._consume_type_ptr_ref_suffix(typ)
                return self.parse_new_suffixed_method(typ)
            if self.peek().type == "IDENT":
                if self.peek(2).type == "LPAREN":
                    typ = self.eat("IDENT").value
                    typ = self._consume_type_ptr_ref_suffix(typ)
                    after = self._next_after_balanced_paren(self.p + 1)
                    if after.type == "LBRACE":
                        return self.parse_function_def(typ, ())
                    return self.parse_var_decl_rest(typ)
                typ = self.eat("IDENT").value
                typ = self._consume_type_ptr_ref_suffix(typ)
                if self.cur().type == "OPERATOR":
                    return self.parse_operator_method(typ)
                return self.parse_var_decl_rest(typ)
            return self.parse_ident_start_stmt()
        raise ParseError(f"unexpected token {t} at {self.cur().line}")

    def parse_scope_spec_raw(self) -> str:
        if self.cur().type == "CLOSURE":
            self.eat("CLOSURE")
            self.eat("LBRACE")
            n = self.eat("NUMBER").value
            self.eat("RBRACE")
            return f"closure{{{n}}}"
        if self.cur().type in ("GLOBAL", "LOCAL", "BUILTINS"):
            s = self.eat().type.lower()
            return s
        raise ParseError(f"bad scope spec at {self.cur().line}")

    def _consume_type_ptr_ref_suffix(self, base: str) -> str:
        while True:
            if self.cur().type == "STAR":
                self.eat("STAR")
                base = f"{base}*"
            elif self.cur().type == "AMP":
                self.eat("AMP")
                base = f"{base}&"
            else:
                break
        return base

    def parse_type_start_stmt(self, is_constexpr: bool = False, is_const: bool = False, is_static: bool = False):
        ret_tok = self.eat()
        ret = _tok_as_type(ret_tok)
        ret = self._consume_type_ptr_ref_suffix(ret)
        if ret_tok.type == "VOID" and self.cur().type == "IDENT" and self.peek().type == "LPAREN":
            if is_const:
                raise ParseError("const 不支持函数定义；请使用 constexpr")
            return self.parse_function_def(ret, (), is_constexpr=is_constexpr)
        if self.cur().type == "OPERATOR":
            return self.parse_operator_method(ret)
        if self.cur().type == "NEW" and self.peek().type == "LT":
            return self.parse_new_suffixed_method(ret)
        if self.cur().type == "IDENT" and self.peek().type == "LPAREN":
            after = self._next_after_balanced_paren(self.p + 1)
            if after.type == "LBRACE":
                if is_const:
                    raise ParseError("const 不支持函数定义；请使用 constexpr")
                if is_static:
                    raise ParseError("static 不支持函数定义")
                return self.parse_function_def(ret, (), is_constexpr=is_constexpr)
            return self.parse_var_decl_rest(ret, is_constexpr=is_constexpr, is_const=is_const, is_static=is_static)
        return self.parse_var_decl_rest(ret, is_constexpr=is_constexpr, is_const=is_const, is_static=is_static)

    def parse_new_suffixed_method(self, ret_type: str):
        """`(public) <类型> New<类名>(签名) { ... }` → 成员名 `New类名`。"""
        self.eat("NEW")
        self.eat("LT")
        target = self.eat("IDENT").value
        self.eat("GT")
        self.eat("LPAREN")
        pt, pn = self.parse_param_list()
        self.eat("RPAREN")
        body_stmts = self.parse_block_raw()
        returns_void = ret_type == "void"
        if returns_void:
            if not body_stmts or not isinstance(body_stmts[-1], ReturnNode):
                body_stmts.append(ReturnNode(None))
        else:
            if not body_stmts or not isinstance(body_stmts[-1], ReturnNode):
                body_stmts.append(ReturnNode(LiteralsNode("0")))
        body = Body(body_stmts)
        name = f"New{target}"
        return FunctionDefNode(name, pt, pn, body, returns_void, (), ret_type)

    def parse_operator_method(self, ret_type: str):
        self.eat("OPERATOR")
        op_suffix = self._parse_operator_symbol()
        self.eat("LPAREN")
        pt, pn = self.parse_param_list()
        self.eat("RPAREN")
        pt = ["instance", *pt]
        pn = ["this", *pn]
        body_stmts = self.parse_block_raw()
        returns_void = ret_type == "void"
        if returns_void:
            if not body_stmts or not isinstance(body_stmts[-1], ReturnNode):
                body_stmts.append(ReturnNode(None))
        else:
            if not body_stmts or not isinstance(body_stmts[-1], ReturnNode):
                body_stmts.append(ReturnNode(LiteralsNode("0")))
        body = Body(body_stmts)
        name = f"__op_{op_suffix}__"
        return FunctionDefNode(name, pt, pn, body, returns_void, (), ret_type)

    def _parse_operator_symbol(self) -> str:
        t = self.cur().type
        if t == "PLUS":
            self.eat("PLUS")
            return "add"
        if t == "MINUS":
            self.eat("MINUS")
            return "sub"
        if t == "STAR":
            self.eat("STAR")
            return "mul"
        if t == "SLASH":
            self.eat("SLASH")
            return "div"
        if t == "PERCENT":
            self.eat("PERCENT")
            return "mod"
        raise ParseError(f"expected operator symbol at {self.cur().line}")

    def parse_var_decl_rest(
        self, typ: str, is_constexpr: bool = False, is_const: bool = False, is_static: bool = False
    ):
        scope = None
        if self.cur().type in ("GLOBAL", "LOCAL", "BUILTINS", "CLOSURE"):
            scope = self.parse_scope_spec_raw()
            self.eat("COLCOL")
        arr_size = None
        arr_elem_type = None
        if self.cur().type == "LBRACKET":
            # 兼容：string[3] name
            self.eat("LBRACKET")
            if self.cur().type != "RBRACKET":
                arr_size = self.parse_expr()
            self.eat("RBRACKET")
            arr_elem_type = typ
            typ = "array"
        name = self.eat("IDENT").value
        if self.cur().type == "LBRACKET":
            # 新语法：string name[3]
            self.eat("LBRACKET")
            if self.cur().type != "RBRACKET":
                arr_size = self.parse_expr()
            self.eat("RBRACKET")
            arr_elem_type = typ
            typ = "array"
        init = None
        if self.cur().type == "LPAREN":
            self.eat("LPAREN")
            args, kwargs = self.parse_call_args()
            self.eat("RPAREN")
            init = FunctionCallNode(VariableLoadNode(typ), args, kwargs)
        elif self.cur().type == "EQ":
            self.eat("EQ")
            init = self.parse_expr()
        self.eat("SEMI")
        if scope:
            return ScopedVarDeclNode(
                typ,
                scope,
                name,
                init,
                array_size_expr=arr_size,
                array_elem_type=arr_elem_type,
                is_constexpr=is_constexpr,
                is_const=is_const,
                is_static=is_static,
            )
        return VarDeclNode(
            typ,
            name,
            init,
            array_size_expr=arr_size,
            array_elem_type=arr_elem_type,
            is_constexpr=is_constexpr,
            is_const=is_const,
            is_static=is_static,
        )

    def parse_function_def(self, ret_type: str, type_params: tuple[str, ...], is_constexpr: bool = False):
        name = self.eat("IDENT").value
        self.eat("LPAREN")
        pt, pn = self.parse_param_list()
        self.eat("RPAREN")
        body_stmts = self.parse_block_raw()
        returns_void = ret_type == "void"
        if returns_void:
            if not body_stmts or not isinstance(body_stmts[-1], ReturnNode):
                body_stmts.append(ReturnNode(None))
        else:
            if not body_stmts or not isinstance(body_stmts[-1], ReturnNode):
                body_stmts.append(ReturnNode(LiteralsNode("0")))
        body = Body(body_stmts)
        fn = FunctionDefNode(name, pt, pn, body, returns_void, type_params, ret_type, is_constexpr=is_constexpr)
        if type_params:
            return TemplateFunctionDefNode(fn)
        return fn

    def parse_param_list(self) -> tuple[list[str], list[str]]:
        pt, pn = [], []
        if self.cur().type == "RPAREN":
            return pt, pn
        while True:
            if self.cur().type == "SLASH":
                self.eat("SLASH")
                if self.cur().type == "COMMA":
                    self.eat("COMMA")
                continue
            if self.cur().type == "STAR" and self.peek().type != "STAR":
                self.eat("STAR")
                self.parse_type_token()
                self.eat("IDENT")
                if self.cur().type == "COMMA":
                    self.eat("COMMA")
                continue
            if self.cur().type == "STARSTAR":
                self.eat("STARSTAR")
                if self.cur().type == "IDENT" and self.peek().type in ("RPAREN", "COMMA"):
                    n = self.eat("IDENT").value
                    pt.append("kwargs")
                    pn.append(n)
                    break
                t = self.parse_type_token()
                t = self._consume_type_ptr_ref_suffix(t)
                n = self.eat("IDENT").value
                pt.append(t)
                pn.append(n)
                break
            t = self.parse_type_token()
            t = self._consume_type_ptr_ref_suffix(t)
            n = self.eat("IDENT").value
            pt.append(t)
            pn.append(n)
            if self.cur().type == "RPAREN":
                break
            self.eat("COMMA")
        return pt, pn

    def parse_type_token(self) -> str:
        if self.cur().type == "TYPENAME":
            self.eat("TYPENAME")
            return f"@{self.eat('IDENT').value}"
        if self.cur().type in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "VOID"):
            return _tok_as_type(self.eat())
        if self.cur().type == "IDENT":
            return self.eat("IDENT").value
        raise ParseError(f"expected type at {self.cur().line}")

    def parse_template_function(self):
        self.eat("TEMPLATE")
        self.eat("LT")
        tparams: list[str] = []
        while True:
            if self.cur().type == "TYPENAME":
                self.eat("TYPENAME")
                tparams.append(self.eat("IDENT").value)
            elif self.cur().type == "IDENT":
                tparams.append(self.eat("IDENT").value)
            else:
                break
            if self.cur().type == "COMMA":
                self.eat("COMMA")
            else:
                break
        self.eat("GT")
        ret = self.parse_type_token()
        ret = self._consume_type_ptr_ref_suffix(ret)
        return self.parse_function_def(ret, tuple(tparams))

    def parse_namespace(self):
        self.eat("NAMESPACE")
        nname = self.eat("IDENT").value
        body = self.parse_block_raw()
        if self.cur().type == "SEMI":
            self.eat("SEMI")
        return NamespaceDefNode(nname, body)

    def parse_class(self):
        self.eat("CLASS")
        cname = self.eat("IDENT").value
        bases: list[tuple[str, str]] = []
        if self.cur().type == "COLON":
            self.eat("COLON")
            while True:
                inherit_access = "private"
                if self.cur().type in ("PUBLIC", "PROTECTED", "PRIVATE"):
                    inherit_access = self.eat().type.lower()
                bname = self.eat("IDENT").value
                bases.append((inherit_access, bname))
                if self.cur().type != "COMMA":
                    break
                self.eat("COMMA")
        self.eat("LBRACE")
        stmts: list = []
        current_access = "private"
        while self.cur().type != "RBRACE":
            if self.cur().type in ("PUBLIC", "PRIVATE", "PROTECTED", "CODE"):
                tag = self.eat()
                self.eat("COLON")
                if tag.type != "CODE":
                    current_access = tag.type.lower()
                while self.cur().type not in ("PUBLIC", "PRIVATE", "PROTECTED", "CODE", "RBRACE", "EOF"):
                    st = self.parse_stmt()
                    setattr(st, "_class_member_access", current_access)
                    stmts.append(st)
            else:
                st = self.parse_stmt()
                setattr(st, "_class_member_access", current_access)
                stmts.append(st)
        self.eat("RBRACE")
        return ClassDefNode(cname, stmts, tuple(bases))

    def parse_struct(self):
        self.eat("STRUCT")
        sname = self.eat("IDENT").value
        self.eat("LBRACE")
        stmts: list = []
        while self.cur().type != "RBRACE":
            stmts.append(self.parse_stmt())
        self.eat("RBRACE")
        return StructDefNode(sname, stmts)

    def parse_block_stmt(self) -> BlockNode:
        return BlockNode(self.parse_block_raw())

    def parse_block_raw(self) -> list:
        self.eat("LBRACE")
        out = []
        while self.cur().type != "RBRACE":
            out.append(self.parse_stmt())
        self.eat("RBRACE")
        return out

    def parse_if_stmt(self) -> IfStmtNode:
        branches: list[tuple] = []
        self.eat("IF")
        self.eat("LPAREN")
        cond0 = self.parse_expr()
        self.eat("RPAREN")
        branches.append((cond0, BlockNode(self.parse_block_raw())))
        while self.cur().type == "ELIF":
            self.eat("ELIF")
            self.eat("LPAREN")
            c = self.parse_expr()
            self.eat("RPAREN")
            branches.append((c, BlockNode(self.parse_block_raw())))
        else_block = None
        if self.cur().type == "ELSE":
            self.eat("ELSE")
            else_block = BlockNode(self.parse_block_raw())
        return IfStmtNode(branches, else_block)

    def parse_while_stmt(self) -> WhileStmtNode:
        self.eat("WHILE")
        self.eat("LPAREN")
        cond = self.parse_expr()
        self.eat("RPAREN")
        return WhileStmtNode(cond, BlockNode(self.parse_block_raw()))

    def parse_for_stmt(self):
        self.eat("FOR")
        self.eat("LPAREN")
        p0 = self.p
        is_range = False
        elem_type = None
        elem_name = None
        try:
            elem_type = self.parse_type_token()
            if self.cur().type != "IDENT":
                raise ParseError("for range needs variable name")
            elem_name = self.eat("IDENT").value
            if self.cur().type == "COLON":
                is_range = True
            else:
                self.p = p0
        except ParseError:
            self.p = p0
            is_range = False
        if is_range:
            self.eat("COLON")
            agg = self.parse_expr()
            self.eat("RPAREN")
            return ForRangeStmtNode(elem_type, elem_name, agg, BlockNode(self.parse_block_raw()))
        init = self.parse_for_c_init()
        self.eat("SEMI")
        cond = None
        if self.cur().type != "SEMI":
            cond = self.parse_expr()
        self.eat("SEMI")
        step = None
        if self.cur().type != "RPAREN":
            step = self.parse_for_assign_or_expr_stmt()
        self.eat("RPAREN")
        return ForCStmtNode(init, cond, step, BlockNode(self.parse_block_raw()))

    def parse_for_c_init(self):
        if self.cur().type == "SEMI":
            return None
        if self.cur().type in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "TYPENAME") or (
            self.cur().type == "IDENT" and self.peek().type == "IDENT"
        ):
            typ = self.parse_type_token()
            typ = self._consume_type_ptr_ref_suffix(typ)
            arr_size = None
            arr_elem_type = None
            if self.cur().type == "LBRACKET":
                self.eat("LBRACKET")
                if self.cur().type != "RBRACKET":
                    arr_size = self.parse_expr()
                self.eat("RBRACKET")
                arr_elem_type = typ
                typ = "array"
            name = self.eat("IDENT").value
            if self.cur().type == "LBRACKET":
                self.eat("LBRACKET")
                if self.cur().type != "RBRACKET":
                    arr_size = self.parse_expr()
                self.eat("RBRACKET")
                arr_elem_type = typ
                typ = "array"
            init = None
            if self.cur().type == "LPAREN":
                self.eat("LPAREN")
                args, kwargs = self.parse_call_args()
                self.eat("RPAREN")
                init = FunctionCallNode(VariableLoadNode(typ), args, kwargs)
            elif self.cur().type == "EQ":
                self.eat("EQ")
                init = self.parse_expr()
            return VarDeclNode(typ, name, init, array_size_expr=arr_size, array_elem_type=arr_elem_type)
        return ExprStmtNode(self.parse_expr())

    def parse_for_assign_or_expr_stmt(self):
        if self.cur().type == "IDENT" and self.peek().type == "EQ":
            n = self.eat("IDENT").value
            self.eat("EQ")
            return AssignStmtNode(n, self.parse_expr())
        if self.cur().type == "IDENT" and self.peek().type in _COMPOUND_ASSIGN_TYPES:
            n = self.eat("IDENT").value
            op = _COMPOUND_ASSIGN_OPS[self.eat().type]
            return CompoundAssignStmtNode(n, op, self.parse_expr())
        return ExprStmtNode(self.parse_expr())

    def parse_switch_stmt(self) -> SwitchStmtNode:
        self.eat("SWITCH")
        self.eat("LPAREN")
        disc = self.parse_expr()
        self.eat("RPAREN")
        self.eat("LBRACE")
        cases: list[tuple] = []
        while self.cur().type == "CASE":
            self.eat("CASE")
            self.eat("LPAREN")
            ce = self.parse_expr()
            self.eat("RPAREN")
            cases.append((ce, BlockNode(self.parse_block_raw())))
        else_block = None
        if self.cur().type == "ELSE":
            self.eat("ELSE")
            else_block = BlockNode(self.parse_block_raw())
        self.eat("RBRACE")
        return SwitchStmtNode(disc, cases, else_block)

    def parse_try_stmt(self) -> TryStmtNode:
        self.eat("TRY")
        try_block = BlockNode(self.parse_block_raw())
        catches: list[tuple[str | None, str | None, BlockNode]] = []
        while self.cur().type == "CATCH":
            self.eat("CATCH")
            type_name: str | None = None
            bind_name: str | None = None
            if self.cur().type == "LPAREN":
                self.eat("LPAREN")
                if self.cur().type != "RPAREN":
                    if self.cur().type in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "VOID"):
                        type_name = _tok_as_type(self.eat())
                        if self.cur().type == "IDENT":
                            bind_name = self.eat("IDENT").value
                    elif self.cur().type == "IDENT":
                        # catch(Exception) / catch(Exception e)
                        type_name = self.eat("IDENT").value
                        if self.cur().type == "IDENT":
                            bind_name = self.eat("IDENT").value
                self.eat("RPAREN")
            catches.append((type_name, bind_name, BlockNode(self.parse_block_raw())))
        else_block = None
        if self.cur().type == "ELSE":
            self.eat("ELSE")
            else_block = BlockNode(self.parse_block_raw())
        finally_block = None
        if self.cur().type == "FINALLY":
            self.eat("FINALLY")
            finally_block = BlockNode(self.parse_block_raw())
        if not catches and finally_block is None:
            raise ParseError("try 语句至少需要 catch 或 finally")
        return TryStmtNode(try_block, catches, else_block, finally_block)

    def parse_import_stmt(self) -> ImportStmtNode:
        self.eat("IMPORT")
        items: list[tuple[int, str, str | None]] = []
        while True:
            rel_level, mod_name = self._parse_module_ref()
            alias = None
            if self.cur().type == "AS":
                self.eat("AS")
                alias = self.eat("IDENT").value
            items.append((rel_level, mod_name, alias))
            if self.cur().type != "COMMA":
                break
            self.eat("COMMA")
        self.eat("SEMI")
        return ImportStmtNode(items)

    def parse_from_import_stmt(self) -> FromImportStmtNode:
        self.eat("FROM")
        rel_level, mod_name = self._parse_module_ref()
        self.eat("IMPORT")
        members: list[tuple[str, str | None]] = []
        while True:
            m = self.eat("IDENT").value
            alias = None
            if self.cur().type == "AS":
                self.eat("AS")
                alias = self.eat("IDENT").value
            members.append((m, alias))
            if self.cur().type != "COMMA":
                break
            self.eat("COMMA")
        self.eat("SEMI")
        return FromImportStmtNode(rel_level, mod_name, members)

    def _parse_module_ref(self) -> tuple[int, str]:
        rel_level = 0
        while self.cur().type == "DOT":
            self.eat("DOT")
            rel_level += 1
        if self.cur().type != "IDENT":
            raise ParseError("import/from 后需要模块名")
        mod_name = self.eat("IDENT").value
        while self.cur().type == "DOT":
            self.eat("DOT")
            mod_name += "." + self.eat("IDENT").value
        return rel_level, mod_name

    def parse_scoped_assign_or_decl(self):
        scope = self.parse_scope_spec_raw()
        self.eat("COLCOL")
        if self.cur().type in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO") and self.peek().type == "IDENT":
            typ = _tok_as_type(self.eat())
            arr_size = None
            arr_elem_type = None
            if self.cur().type == "LBRACKET":
                self.eat("LBRACKET")
                if self.cur().type != "RBRACKET":
                    arr_size = self.parse_expr()
                self.eat("RBRACKET")
                arr_elem_type = typ
                typ = "array"
            name = self.eat("IDENT").value
            if self.cur().type == "LBRACKET":
                self.eat("LBRACKET")
                if self.cur().type != "RBRACKET":
                    arr_size = self.parse_expr()
                self.eat("RBRACKET")
                arr_elem_type = typ
                typ = "array"
            init = None
            if self.cur().type == "EQ":
                self.eat("EQ")
                init = self.parse_expr()
            self.eat("SEMI")
            return ScopedVarDeclNode(typ, scope, name, init, array_size_expr=arr_size, array_elem_type=arr_elem_type)
        name = self.eat("IDENT").value
        if self.cur().type in _COMPOUND_ASSIGN_TYPES:
            op = _COMPOUND_ASSIGN_OPS[self.eat().type]
            e = self.parse_expr()
            self.eat("SEMI")
            return ScopedCompoundAssignStmtNode(scope, name, op, e)
        self.eat("EQ")
        e = self.parse_expr()
        self.eat("SEMI")
        return ScopedAssignStmtNode(scope, name, e)

    def _finish_expr_stmt_from_lhs(self, ex):
        if self.cur().type == "EQ":
            self.eat("EQ")
            rhs = self.parse_expr()
            self.eat("SEMI")
            if isinstance(ex, ScopedLoadNode):
                return ScopedAssignStmtNode(ex.scope, ex.name, rhs)
            if isinstance(ex, VariableLoadNode):
                return AssignStmtNode(ex.name, rhs)
            if isinstance(ex, AttributeAccessNode):
                from .AST.Data import AttributeStoreNode

                return ExprStmtNode(AttributeStoreNode(ex.obj, ex.attr, rhs))
            if isinstance(ex, IndexAccessNode):
                return ExprStmtNode(IndexStoreNode(ex.obj, ex.index, rhs))
            raise ParseError("invalid assignment target")
        if self.cur().type in _COMPOUND_ASSIGN_TYPES:
            op = _COMPOUND_ASSIGN_OPS[self.eat().type]
            rhs = self.parse_expr()
            self.eat("SEMI")
            if isinstance(ex, ScopedLoadNode):
                return ScopedCompoundAssignStmtNode(ex.scope, ex.name, op, rhs)
            if isinstance(ex, VariableLoadNode):
                return CompoundAssignStmtNode(ex.name, op, rhs)
            raise ParseError("compound assignment requires a variable or scoped variable target")
        self.eat("SEMI")
        return ExprStmtNode(ex)

    def parse_ident_start_stmt(self):
        name = self.eat("IDENT").value
        if self.cur().type == "COLCOL":
            self.eat("COLCOL")
            second = self.eat("IDENT").value
            base: object = ScopedLoadNode(name, second)
        else:
            base = VariableLoadNode(name)
        ex = self._parse_postfix_continue(base)
        return self._finish_expr_stmt_from_lhs(ex)

    def _parse_postfix_continue(self, base):
        while True:
            if self.cur().type == "LT" and self.peek().type == "LT":
                self.eat("LT")
                self.eat("LT")
                self._parse_template_args()
                self.eat("GT")
                self.eat("GT")
                continue
            if self.cur().type == "LPAREN":
                self.eat("LPAREN")
                args, kwargs = self.parse_call_args()
                self.eat("RPAREN")
                base = FunctionCallNode(base, args, kwargs)
            elif self.cur().type in ("DOT", "ARROW"):
                self.eat()
                attr = self.eat("IDENT").value
                base = AttributeAccessNode(base, attr)
            elif self.cur().type == "LBRACKET":
                self.eat("LBRACKET")
                idx = self.parse_expr()
                self.eat("RBRACKET")
                base = IndexAccessNode(base, idx)
            elif self.cur().type == "LT" and self.peek().type == "LT":
                self.eat("LT")
                self.eat("LT")
                self._parse_template_args()
                self.eat("GT")
                self.eat("GT")
            else:
                break
        return base

    def _parse_template_args(self):
        while True:
            self.parse_type_token()
            if self.cur().type == "COMMA":
                self.eat("COMMA")
            else:
                break

    def parse_call_args(self):
        args = []
        kwargs = {}
        if self.cur().type == "RPAREN":
            return args, kwargs
        while True:
            if self.cur().type == "IDENT" and self.peek().type == "EQ" and self.peek(2).type != "EQ":
                k = self.eat("IDENT").value
                self.eat("EQ")
                kwargs[k] = self.parse_expr()
            else:
                args.append(self.parse_expr())
            if self.cur().type == "COMMA":
                self.eat("COMMA")
            else:
                break
        return args, kwargs

    def parse_expr(self):
        return self.parse_logical_or()

    def parse_logical_or(self):
        left = self.parse_logical_and()
        while self.cur().type == "LOGIC_OR":
            self.eat("LOGIC_OR")
            right = self.parse_logical_and()
            left = BinOpNode(left, BinOperator.lor, right)
        return left

    def parse_logical_and(self):
        left = self.parse_relational()
        while self.cur().type == "LOGIC_AND":
            self.eat("LOGIC_AND")
            right = self.parse_relational()
            left = BinOpNode(left, BinOperator.land, right)
        return left

    def parse_relational(self):
        left = self.parse_shift()
        relmap = {
            "LT": BinOperator.lt,
            "LE": BinOperator.le,
            "GT": BinOperator.gt,
            "GE": BinOperator.ge,
            "EQEQ": BinOperator.eq,
            "NE": BinOperator.ne,
        }
        while self.cur().type in relmap:
            op = relmap[self.eat().type]
            right = self.parse_shift()
            left = BinOpNode(left, op, right)
        return left

    def parse_shift(self):
        left = self.parse_additive()
        while True:
            if self.cur().type == "LT" and self.peek().type == "LT":
                self.eat("LT")
                self.eat("LT")
                right = self.parse_additive()
                left = BinOpNode(left, BinOperator.shl, right)
            elif self.cur().type == "GT" and self.peek().type == "GT":
                self.eat("GT")
                self.eat("GT")
                right = self.parse_additive()
                left = BinOpNode(left, BinOperator.shr, right)
            else:
                break
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.cur().type in ("PLUS", "MINUS"):
            op = BinOperator.add if self.eat().type == "PLUS" else BinOperator.sub
            right = self.parse_multiplicative()
            left = BinOpNode(left, op, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        mmap = {"STAR": BinOperator.mul, "SLASH": BinOperator.div, "PERCENT": BinOperator.mod}
        while self.cur().type in mmap:
            op = mmap[self.eat().type]
            right = self.parse_unary()
            left = BinOpNode(left, op, right)
        return left

    def parse_unary(self):
        if self.cur().type == "BANG":
            self.eat("BANG")
            return UnaryOpNode(UnaryOperator.lnot, self.parse_unary())
        if self.cur().type == "AMP":
            self.eat("AMP")
            return UnaryOpNode(UnaryOperator.addr, self.parse_unary())
        if self.cur().type == "STAR":
            self.eat("STAR")
            return UnaryOpNode(UnaryOperator.deref, self.parse_unary())
        if self.cur().type == "MINUS":
            self.eat("MINUS")
            return UnaryOpNode(UnaryOperator.neg, self.parse_unary())
        if self.cur().type == "TILDE":
            self.eat("TILDE")
            return UnaryOpNode(UnaryOperator.bitnot, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.cur().type
        if t == "TRUE":
            self.eat("TRUE")
            return BoolLiteralNode(True)
        if t == "FALSE":
            self.eat("FALSE")
            return BoolLiteralNode(False)
        if t == "NUMBER":
            v = self.eat().value
            return LiteralsNode(str(v))
        if t == "STRING_LIT":
            s = self.eat().value
            return LiteralsNode(f'"{s}"')
        if t == "THIS":
            self.eat("THIS")
            base = VariableLoadNode("this")
            return self._parse_postfix_continue(base)
        if t == "BASE":
            self.eat("BASE")
            base = VariableLoadNode("base")
            return self._parse_postfix_continue(base)
        if t == "LPAREN":
            self.eat("LPAREN")
            e = self.parse_expr()
            self.eat("RPAREN")
            return e
        if t == "LBRACKET":
            self.eat("LBRACKET")
            elems = []
            if self.cur().type != "RBRACKET":
                while True:
                    elems.append(self.parse_expr())
                    if self.cur().type == "COMMA":
                        self.eat("COMMA")
                        continue
                    break
            self.eat("RBRACKET")
            return ArrayLiteralNode(elems)
        if t == "LBRACE":
            self.eat("LBRACE")
            elems = []
            if self.cur().type != "RBRACE":
                while True:
                    elems.append(self.parse_expr())
                    if self.cur().type == "COMMA":
                        self.eat("COMMA")
                        continue
                    break
            self.eat("RBRACE")
            return ArrayLiteralNode(elems)
        if t in ("GLOBAL", "LOCAL", "BUILTINS", "CLOSURE"):
            scope = self.parse_scope_spec_raw()
            self.eat("COLCOL")
            name = self.eat("IDENT").value
            base = ScopedLoadNode(scope, name)
            return self._parse_postfix_continue(base)
        if t == "IDENT":
            name = self.eat("IDENT").value
            if self.cur().type == "COLCOL":
                self.eat("COLCOL")
                second = self.eat("IDENT").value
                base = ScopedLoadNode(name, second)
            else:
                base = VariableLoadNode(name)
            return self._parse_postfix_continue(base)
        raise ParseError(f"bad primary {t} at {self.cur().line}")


def _tok_as_type(tok: Token) -> str:
    return {
        "INT": "int",
        "FLOAT": "float",
        "BOOL": "bool",
        "STRING": "string",
        "ARRAY": "array",
        "AUTO": "auto",
        "VOID": "void",
    }[tok.type]
