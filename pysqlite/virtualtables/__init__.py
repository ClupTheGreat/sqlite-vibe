from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pysqlite.schema import Schema


class VirtualTable:
    name: str
    module: str
    args: list[str]
    columns: list[str]

    def close(self):
        pass


_registered_modules: dict[str, type[VirtualTable]] = {}
_module_instances: dict[str, VirtualTable] = {}


def register_module(name: str, cls: type[VirtualTable]):
    _registered_modules[name] = cls


def get_module_class(name: str) -> type[VirtualTable] | None:
    return _registered_modules.get(name)


def list_modules() -> list[str]:
    return list(_registered_modules.keys())


def create_virtual_table(name: str, module: str, args: list[str],
                         schema: 'Schema | None' = None) -> VirtualTable | None:
    cls = get_module_class(module)
    if cls is None:
        return None
    config = {}
    inst = cls(name, args, config)
    _module_instances[name.upper()] = inst
    if schema:
        schema.virtual_tables[name.upper()] = inst
    return inst


def get_virtual_table(name: str, schema: 'Schema | None' = None
                      ) -> VirtualTable | None:
    if schema:
        return schema.virtual_tables.get(name.upper())
    return _module_instances.get(name.upper())


def drop_virtual_table(name: str, schema: 'Schema | None' = None):
    key = name.upper()
    inst = None
    if schema:
        inst = schema.virtual_tables.pop(key, None)
    else:
        inst = _module_instances.pop(key, None)
    if inst:
        inst.close()


# Import and register built-in virtual table modules (after definitions to avoid circular imports)
from pysqlite.virtualtables import fts5  # noqa: F401, E402
