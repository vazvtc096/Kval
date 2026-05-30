from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Union
import builtins


@dataclass
class Object:
    type: Type
    namespace: dict[str, Object]

@dataclass
class Type:
    type: Type
    name: str
    bases: tuple[Type]
    namespace: dict[str, Object]
    def __post_init__(self):
        self.namespace['mro'] = self.mro

    def mro(self, _visited=None) -> list[Type]:
        if _visited is None:
            _visited = set()
        
        if id(self) in _visited:
            return [self]
        
        _visited.add(id(self))

        def merge(seqs):
            result = []
            while True:
                candidate = None
                for seq in seqs:
                    if seq:
                        candidate = seq[0]
                        valid = True
                        for other in seqs:
                            if candidate in other[1:]:
                                valid = False
                                break
                        if valid:
                            break
                        candidate = None
                if candidate is None:
                    break
                result.append(candidate)
                for seq in seqs:
                    if seq and seq[0] == candidate:
                        seq.pop(0)
            return result
        
        seqs = []
        for base in self.bases:
            seqs.append(base.mro(_visited).copy())
        seqs.append(list(self.bases))
        
        mro_list = [self] + merge(seqs)
        return mro_list


object = Type(
    None,
    'object', None, {
        'object_new': lambda cls, *args, **kwargs: Object(cls, {})
    }
)

def type_call(cls: Union[ObjectAttributeVisitor, Type], *args, **kwargs) -> Object:
    obj = object.namespace['object_new'](cls, *args, **kwargs)
    oav_obj = ObjectAttributeVisitor(obj)
    if isinstance(cls, ObjectAttributeVisitor):
        ori = ObjectAttributeVisitor.return_ori
        ObjectAttributeVisitor.return_ori = True
        init = cls.__init__ or (lambda self, *args, **kwargs: None)
        init(oav_obj, *args, **kwargs)
        ObjectAttributeVisitor.return_ori = ori
    else:
        init = cls.namespace.get(
            _ObjectAttributeModifier.name(cls, '__init__'),
            lambda self, *args, **kwargs: None
        )
        init(oav_obj, *args, **kwargs)
    return obj
type = Type(
    None,
    'type', (object,), {
        'type_new': lambda metaclass, name, bases, namespace: Type(
            metaclass, name, bases or (object,), namespace
        ),
        'type_call': type_call
    }
)

object.type = type
object.bases = (object,)
type.type = type

def create_type(name, bases, dict) -> Type:
    return Type(
        type,
        name,
        tuple(
            sub_c for sub_c in bases if isinstance(sub_c, Type)
        ) or (object,),
        {
            _ObjectAttributeModifier.name(Type(type, name, (), {}), attr_name): value
            for attr_name, value in dict.items()
        }
    )

class _ObjectAttributeModifier:
    def name(obj: Union[Object, Type], method_name: str):
        method_name = (
            obj.type.name + '_' + method_name[2:-2]
            if method_name.startswith('__') and method_name.endswith('__') else
            method_name
        )
        return method_name
    def obj(obj: Union[Object, Type], method_name: str):
        return obj.namespace[_ObjectAttributeModifier.name(obj, method_name)]

class _Undefined:
    def __bool__(self):
        return False
_undefined = _Undefined()

class ObjectAttributeVisitor:
    obj = _undefined
    return_ori = False
    def __init__(self, obj: Union[Object, Type]):
        self.obj = obj
    def __getattribute__(self, name):
        obj: Union[Object, Type, _Undefined] = super().__getattribute__('obj')
        return_ori = super().__getattribute__('return_ori')

        if isinstance(obj, (Object, Type)):
            if name in obj.namespace:
                ret = obj.namespace[name]
            elif any([
                _ObjectAttributeModifier.name(base, name) in base.namespace
                for base in obj.type.mro()
            ]):
                for base in obj.type.mro():
                    if _ObjectAttributeModifier.name(base, name) in base.namespace:
                        ret = base.namespace[_ObjectAttributeModifier.name(base, name)]
                        break
            else:
                return _undefined
            
            if callable(ret) and not isinstance(ret, StaticMethod) and not return_ori:
                return partial(ret, self)
            else:
                return ret
        else:
            return builtins.type(obj).__getattribute__(obj, name)
    def __setattr__(self, name, value):
        obj: Union[Object, Type, _Undefined] = super().__getattribute__('obj')

        if isinstance(obj, (Object, Type)):
            if obj is _undefined:
                super().__setattr__('obj', value)
            else:
                obj.namespace[name] = value
        else:
            builtins.type(obj).__setattr__(obj, name, value)
    def __str__(self):
        obj: Union[Object, Type] = super().__getattribute__('obj')
        return f"[{obj.type.name} OAV: {obj.namespace} - {obj.type} - {obj.type.mro} - {dir(obj.type)}]"

class StaticMethod:
    def __init__(self, func):
        self.func = func
    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)