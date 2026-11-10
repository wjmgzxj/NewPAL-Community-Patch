"""Select a map-test ABI by exact relevant bytes, never whole-EXE hashes.

Pure disk/byte comparison only. No process opening, memory writes or code scanning
for guessed addresses. Contracts are explicit audited reference regions.
"""
import struct
import flash_v4 as pe
from settings_toggle_v1 import imports

GLOBALS = (0x531b80, 0x531b7c, 0x56ffc0, 0x56ffc4, 0x53a605,
           0x53b628, 0x5628e8, 0x53b8d8, 0x53a5fc, 0x52cda0,
           0x53e8c8, 0x53d064, 0x53a584)


def read_region(data, rva, size):
    at = pe.rva_offset(data, rva)
    end = pe.rva_offset(data, rva + size - 1)
    if size <= 0 or end != at + size - 1 or at + size > len(data):
        raise ValueError('传送接口区域不完整')
    return bytes(data[at:at + size])


def select_contract(data, manifest):
    try:
        header, opt, sections = pe.pe_info(data)
        if struct.unpack_from('<H', data, header + 4)[0] != 0x14c:
            raise ValueError('非32位x86游戏')
        if struct.unpack_from('<H', data, opt)[0] != 0x10b:
            raise ValueError('非32位PE游戏')
        if struct.unpack_from('<I', data, opt + 28)[0] != 0x400000:
            raise ValueError('游戏映像基址已改变')
        # Do not infer a new global layout from similarly named files/prologues.
        for address in GLOBALS:
            rva = address - 0x400000
            matches = [i for i, s in enumerate(sections)
                       if s[2] <= rva < s[2] + max(s[1], s[3])]
            if len(matches) != 1:
                raise ValueError('游戏数据布局不匹配')
            section_header = opt + struct.unpack_from('<H', data, header + 20)[0] + matches[0] * 40
            if struct.unpack_from('<I', data, section_header + 36)[0] & 0xc0000000 != 0xc0000000:
                raise ValueError('游戏状态区读写属性不匹配')
        iat = imports(data)
        matches = []
        for contract in manifest['contracts']:
            if iat.get('SDL_GetTicks') != 0x400000 + contract['ticks_iat_rva']:
                continue
            if all(read_region(data, row['rva'], len(bytes.fromhex(row['bytes']))) ==
                   bytes.fromhex(row['bytes']) for row in contract['regions']):
                matches.append(contract)
        if len(matches) != 1:
            raise ValueError('传送接口不兼容或无法唯一识别')
        return matches[0]
    except (KeyError, IndexError, struct.error) as error:
        raise ValueError('游戏EXE结构不完整，无法核对传送接口') from error


def validate_runtime(read_rva, base, contract):
    """Read-only check before any bridge connection/write; read_rva(rva,n)."""
    if contract['kind'] == 'integrated' and base != 0x400000:
        raise ValueError('内置测试桥不支持此次映像重定位')
    delta = base - 0x400000
    relocations = contract.get('relocations', [])
    for row in contract['regions']:
        if row.get('attach_owned', False):
            # Portable attach validates these atomically, and can recognize a
            # previously installed identical dormant RAM bridge at these sites.
            continue
        expected = bytearray.fromhex(row['bytes'])
        for rva in relocations:
            offset = rva - row['rva']
            if 0 <= offset and offset + 4 <= len(expected):
                old = struct.unpack_from('<I', expected, offset)[0]
                struct.pack_into('<I', expected, offset, (old + delta) & 0xffffffff)
        if read_rva(row['rva'], len(expected)) != bytes(expected):
            raise ValueError('运行中的传送接口与已核对代码不符，拒绝连接')
