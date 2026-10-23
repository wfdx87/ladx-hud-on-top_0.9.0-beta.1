"""
hud-on-top 0.9.0-beta.1 for native Rev2 and ladxvwf10.


The original ladxvwf10 patch is not included.
"""
import struct
import zlib

VERSION = (0, 9, 0)
RELEASE = "0.9.0-beta.1"
PRERELEASE = b"beta.1"
MARKER = 0xFFF57
MAGIC = b'WFHUDTOP'

# Integration note for ROM editors and other enhancement patches:
# Reserve ROM offsets 0xFFF00..0xFFFFF (bank 0x3F, CPU 0x7F00..0x7FFF)
# for the HUD helper, identification/version header and relocated handler.
# Shared data pools must end before 0xFFF00. Additional hooks and checked
# padding islands are documented at their write sites below. This installer
# verifies expected bytes before use; it does not relocate another patch's
# code or allocate/reserve that patch's storage on its behalf. Integrations
# must coordinate those boundaries and preserve these bytes when saving.


class Code:
    def __init__(self): self.bytes=bytearray(); self.refs=[]; self.labels={}
    def emit(self, value): self.bytes.extend(bytes.fromhex(value)); return self
    def label(self, name): self.labels[name]=len(self.bytes); return self
    def branch(self, opcode, label):
        self.emit(opcode); self.refs.append((len(self.bytes), label, True)); self.bytes.append(0); return self
    def address(self, opcode, label):
        self.emit(opcode); self.refs.append((len(self.bytes), label, False)); self.bytes.extend(b'\0\0'); return self
    def resolve(self, base, symbols):
        raw=bytearray(self.bytes)
        for at,label,relative in self.refs:
            destination=base+self.labels[label] if label in self.labels else symbols[label]
            if relative:
                displacement=destination-(base+at+1)
                if not -128<=displacement<=127:raise ValueError('Internal branch out of range.')
                raw[at]=displacement&255
            else:raw[at:at+2]=struct.pack('<H',destination)
        return raw


def unique(data, signature, start=0, end=0x4000):
    hits=[]; at=start
    while True:
        at=data.find(signature,at,end)
        if at<0:break
        hits.append(at);at+=1
    if len(hits)!=1:raise ValueError('ROM code does not match the supported English Rev 2 layout.')
    return hits[0]


def assemble(original_lcd, fallback_bank=0x3F, fallback_address=0x7F77):
    routines={}
    # Z iff world gameplay has the normal HUD, including loading and room scrolling.
    # Dialogs deliberately remain active: their BG drawing follows the room offset.
    # Honor intentional HUD hiding during instrument hints and other cutscenes.
    # Keep the mode/subtype policy, then require the LCDC shadow's WINON bit.
    routines['guard']=(Code().emit('FA 95 DB D6 0B FE 02').branch('38','window')
        .emit('C6 05 E6 FE C0 FA 96 DB E6 FC C0')
        .label('window').emit('FA FD D6 2F E6 20 C0 FA 9A DB FE 80 C9'))

    # Original WY write always runs. Only our own LYC=15 split is disabled on fallback.
    # SET preserves HL here and saves space without borrowing the debug switches.
    routines['setup']=(Code().address('CD','guard')
        .branch('28','active').emit('FA 9A DB E0 4A F0 45 FE 0F C0 3E 4F E0 45 F0 FF E6 FD E0 FF F0 40 F6 02 E0 40 E5 21 FD D6 CB CE E1 C9')
        .label('active').address('CD','arm')
        .emit('F0 44 C6 70 E6 80').branch('28','top')
        .emit('F0 40 E6 DF E0 40 C9')
        .label('top').emit('F0 40 E6 FD F6 20 E0 40 C9'))
    # Switch at HBlank after scanline 15, or catch up if loading delayed it.
    # Ignore only early stale requests; a late request must still hide the window.
    # Preserve AF for the old interrupt path.
    routines['lcd']=(Code().emit('F5 F0 45 FE 0F').branch('20','original')
        .emit('F0 44 D6 0F FE 81').branch('30','return')
        .label('wait').emit('F0 41 E6 03').branch('20','wait')
        .emit('F0 40 E6 DF F6 02 E0 40 F0 FC E0 42').label('return').emit('F1 D9')
        .label('original').emit(f'3E {fallback_bank:02X} EA 00 21 C3 {(fallback_address+2)&255:02X} {(fallback_address+2)>>8:02X}'))
    # Add C to each sprite Y. Main logic and OAM staging coordinates stay unchanged.
    routines['shift']=(Code().emit('21 00 C0 06 28').label('loop')
        .emit('7E 81 77 2C 2C 2C 2C 05').branch('20','loop').emit('C9'))
    routines['begin']=(Code().emit('3E 01 E0 FD C5 E5 F0 45 FE 0F')
        .branch('20','done').emit('0E F0').address('CD','shift')
        .label('done').emit('E1 C1 C9'))
    routines['end']=(Code().address('CD','switch').address('CD','guard').emit('C0 0E 10').emit(routines['shift'].bytes.hex()))
    routines['end'].labels.update({name:at+9 for name,at in routines['shift'].labels.items()})
    routines['end'].refs.extend((at+9,name,relative) for at,name,relative in routines['shift'].refs)
    del routines['shift']
    # Main-loop draws are shifted by end(); only VBlank draws need it here.
    routines['link']=(Code().address('CD','guard').branch('20','base')
        .emit('F0 FD A7').label('base').emit('FA 3B C1 C0 C6 10 C9'))
    # Prime only the window/sprite control at interrupt entry, before the
    # original VBlank work. AF is pushed exactly once for the native epilogue.
    routines['prime']=(Code().emit('F5 F0 45 FE 0F').branch('20','native')
        .emit('F0 40 E6 FD F6 20 E0 40').label('native').address('C3','vblank_original'))
    routines['restore']=Code().emit('FA AF DB EA 00 21 79 E0 70 C1 D1 E1 F1 D9')
    # The original caller executes EI immediately after this hook. Restore IE
    # after loading without a redundant DI; both return paths are safe there.
    routines['load']=(Code().address('CD','guard').address('C2','load_original')
        .emit('F0 FF F5 E6 02 E0 FF FB').address('CD','load_original')
        .emit('F1 E0 FF C9'))
    # LoadRoom normally resets IE to VBlank only; retain STAT for the HUD.
    routines['room']=(Code().address('CD','guard').emit('3E 01').address('CA','stat_on').emit('E0 FF C9'))
    # One shared arm sequence for main-loop setup and LCD restarts.
    routines['arm']=Code().emit('AF E0 4A 3E 0F E0 45 F0 FF').address('C3','stat_on')
    routines['stat_on']=Code().emit('F6 02 E0 FF C9')
    # Clear only stale STAT requests; keep VBlank and other requests intact.
    # Retain the prepared scroll value and enable the LCD only after arming.
    routines['enable']=(Code().emit('F5').address('CD','guard').branch('20','plain')
        .address('CD','arm').emit('F0 0F E6 FD E0 0F FA FD D6 E6 FD F6 20 E0 40')
        .address('C3','enable_done').label('plain').emit('F1 FA FD D6 E0 40 C9'))
    routines['enable_done']=Code().emit('F1 FA FD D6 C9')
    # Called after WRAM bank 1 is restored. Entry already executed EI and
    # the preserved copy body has no DI, so another EI is unnecessary.
    routines['map_leave']=Code().emit('F0 80 E0 FF').address('C3','draw_link')
    # Oracle-style prepared scroll register: the split writes a stable value,
    # rather than subtracting from a register an interrupt may already adjust.
    # FFFC is explicitly unused in the supported game's HRAM layout.
    # Prepare once, then write the same adjusted value used by the split.
    # LYC=15 identifies the current hardware viewport. Native screens keep SCY.
    routines['scroll']=(Code().emit('D6 10 E0 FC F0 45 FE 0F F0 FC')
        .branch('28','write').emit('C6 10').label('write').address('C3','finish_scroll'))
    routines['finish_scroll']=Code().emit('E0 42 F0 96 C9')
    # VWF palette expansion uses a mirrored bank-local gateway. Split setup's two
    # return paths so all HUD code fits the remaining verified ROM0 holes.
    setup = routines['setup']
    cut = setup.labels['active']
    active = Code(); active.bytes = setup.bytes[cut:]
    active.labels = {n:o-cut for n,o in setup.labels.items() if o>=cut}
    active.refs = [(o-cut,n,rel) for o,n,rel in setup.refs if o>=cut]
    setup.bytes = setup.bytes[:cut]
    setup.bytes[3:5] = bytes.fromhex('CA 00 00')
    setup.labels = {}
    setup.refs = [(1,'guard',False),(4,'setup_active',False)]
    routines['setup_active'] = active
    # Share the identical LCDC top-of-frame write between setup and VBlank.
    active = routines['setup_active']; cut = active.labels['top']
    active.bytes[cut:] = bytes.fromhex('C3 00 00')
    active.refs.append((cut+1,'top_control',False))
    routines['top_control'] = Code().emit('F0 40 E6 FD F6 20 E0 40 C9')
    prime = routines['prime']
    prime.bytes[7:15] = bytes.fromhex('CD 00 00')
    prime.labels['native'] -= 5
    prime.refs = [(o-5 if o>=15 else o,n,rel) for o,n,rel in prime.refs]
    prime.refs.append((8,'top_control',False))
    routines['prime'] = Code().emit('F5 F0 45 FE 0F').address('CC','top_control').address('C3','vblank_original')
    return routines


def allocate(routines, native_region=(0x37F,0x408), native=False):
    # 0003–0005 are live debug switches, even though all three bytes are zero.
    # VWF has live code at 3FED..3FFC; leave that entire region untouched.
    # The direction and Ghini trampolines at 3970–397A and 3E29–3E33
    # are marked unused. Their bytes and absence of direct callers are checked.
    stub_a,stub_b = ((0x3967,0x3972),(0x3E20,0x3E2B)) if native else ((0x3970,0x397B),(0x3E29,0x3E34))
    regions=((0x0006,0x0040),(0x0091,0x0100),
             (0x0043,0x0048),(0x004B,0x0050),(0x0051,0x0058),(0x005B,0x0060),native_region,stub_a,stub_b)
    ordered=sorted(routines,key=lambda n:len(routines[n].bytes),reverse=True)
    def place(index,cursors,symbols):
        if index==len(ordered):return symbols
        name=ordered[index];size=len(routines[name].bytes)
        choices=sorted((i for i,(a,b) in enumerate(regions) if cursors[i]+size<=b),
                       key=lambda i:regions[i][1]-cursors[i]-size)
        for i in choices:
            next_cursors=list(cursors);next_cursors[i]+=size
            answer=place(index+1,next_cursors,dict(symbols,**{name:cursors[i]}))
            if answer is not None:return answer
        return None
    symbols=place(0,[a for a,b in regions],{})
    if symbols is None:raise ValueError('Internal error: patch routines exceed reserved space.')
    symbols['shift']=symbols['end']+9
    return symbols,regions


def patch_inventory_palette_copies(data, output):
    # Bank 20 ends at 7F19 in the supported revision. This zero tail is not
    # inferred from arbitrary zero runs: it follows the disassembly's final RET.
    bank_start = 0x80000
    cursor = bank_start + 0x3F20
    limit = bank_start + 0x4000
    if any(data[cursor:limit]):
        raise ValueError('Inventory-bank padding is occupied. No output written.')
    blocks = (
        ('F3 AF E0 70 46 3E 03 E0 70 70 23 0D 79 A7 20 F1 AF E0 70 FB', True),
        ('F3 3E 03 E0 70 46 3D E0 70 70 23 0D 79 A7 20 F1 AF E0 70', False),
    )
    for signature, enable_on_return in blocks:
        expected = bytes.fromhex(signature)
        at = unique(data, expected, bank_start, bank_start+0x4000)
        # IE is saved on the stack; VBlank is masked while STAT remains able
        # to cut the HUD off. The HUD handler uses HRAM only and preserves AF,
        # so it can interrupt copies with WRAM bank 3 selected.
        # Relative loop branches stay unchanged within the copied block.
        body = expected[1:-1] if enable_on_return else expected[1:]
        prefix = bytes.fromhex('F0 FF F5 E6 02 E0 FF FB')
        suffix = bytes.fromhex('F3 F1 E0 FF AF')
        if enable_on_return:
            suffix += bytes.fromhex('FB')
        suffix += bytes.fromhex('C9')
        code = prefix + body + suffix
        if cursor+len(code) > limit:
            raise ValueError('Inventory interrupt wrappers exceed reserved space.')
        output[cursor:cursor+len(code)] = code
        address = 0x4000 + cursor-bank_start
        # Replace the entire block with CALL/NOP padding. The return path
        # resumes exactly after the original block with A=0 and Z set.
        output[at:at+len(expected)] = b'\xCD' + struct.pack('<H', address) + bytes(len(expected)-3)
        cursor += len(code)


def patch_map_save_palette_copies(data, output, leave_at, native=False):
    # Native uses its checked final tail; VWF uses two explicitly checked
    # padding islands between existing VWF code/data, preserving the font table.
    start, limit = (0x7FE8,0x8000) if native else (0x7E02,0x7E11)
    second, second_limit = 0x7F92, 0x7FA0
    if any(data[start:limit]) or (not native and any(data[second:second_limit])):
        raise ValueError('Map/save wrapper padding is occupied.')
    # FF80/FF81 are explicitly unused in HRAM. They save IE and the bank-3
    # flag. These main-thread wrappers cannot nest; IRQs do not use them.
    # Never RET with bank 3 selected: the real stack lives at DFFF.
    # Read the bank-3 flag into unused HRAM, restore bank 1, then return.
    enter = bytes.fromhex('F0 FF E0 80 E6 02 E0 FF FB 3E 03 E0 70 FA 00 D0 E0 81 AF E0 70 F0 81 C9')
    signature=bytes.fromhex('F3 3E 03 E0 70 FA 00 D0 A7 20 14 AF E0 70 46 3E 03 E0 70 70 23 0D 79 A7 20 F1 3E 01 EA 00 D0 AF E0 70 FB CD')
    positions=[]
    at=0x4000
    while True:
        at=data.find(signature, at, 0x8000)
        if at<0:break
        positions.append(at);at+=1
    if len(positions)!=2:
        raise ValueError('Map/save palette-copy layout is unsupported.')
    targets={int.from_bytes(data[at+len(signature):at+len(signature)+2],'little') for at in positions}
    if targets!={unique(data,bytes.fromhex('F0 9D 3C C8 F0 FE A7'),0x1D00,0x1D50)}:
        raise ValueError('Map/save sprite-redraw targets disagree.')
    # The VWF bank-1 tail is live. Two checked padding islands hold the
    # wrapper: switch to the second island after LD A,3 but BEFORE selecting
    # WRAM bank 3. No CALL/RET ever uses the wrong WRAM stack bank.
    if native:
        if start+len(enter)>limit:raise ValueError('Map/save wrapper exceeds padding.')
        output[start:start+len(enter)]=enter
    else:
        first=enter[:11]+b'\xC3'+struct.pack('<H',second)
        rest=enter[11:]
        if start+len(first)>limit or second+len(rest)>second_limit:
            raise ValueError('Map/save split wrapper exceeds reserved padding.')
        output[start:start+len(first)]=first
        output[second:second+len(rest)]=rest
    for at in positions:
        # Preserve all internal branches, WRAM work, and conditional copy logic.
        # Flag read is now inside the wrapper; original AND/JR stay in place.
        output[at:at+8]=b'\xCD'+struct.pack('<H',start)+bytes(5)
        end=at+len(signature)-2  # EI followed by CALL DrawLinkSprite.
        output[end:end+4]=b'\xCD'+struct.pack('<H',leave_at)+b'\0'


def patch_intro_palette_calls(data, output, switch, native=False):
    # These three entry points are called only from bank 1 (intro/game over).
    # Their stock callsb selects bank 20 without updating wCurrentBank. The
    # relocated LCD IRQ MUST see the actual bank when it interrupts that code.
    # SwitchBank runs from ROM0 on both entry and exit. Never unmap bank 20
    # while a return address or instruction still needs to execute there.
    calls = (((0x8D2,0x6A38),(0x8E1,0x6AC9),(0x8EB,0x6BAC)) if native else
             ((0x8D7,0x6A30),(0x8E6,0x6AC1),(0x8F0,0x6BA4)))
    for i, (trampoline, target) in enumerate(calls):
        expected = bytes.fromhex('3E 20 EA 00 21 CD') + struct.pack('<H',target)
        if data[trampoline:trampoline+8] != expected:
            raise ValueError('Intro palette trampoline is modified or unsupported.')
        address = 0x7FC0+i*8
        offset = 0x80000+address-0x4000
        if any(data[offset:offset+8]):
            raise ValueError('Intro palette wrapper space is occupied. No output written.')
        output[trampoline+2:trampoline+5] = b'\xCD'+struct.pack('<H',switch)
        output[trampoline+6:trampoline+8] = struct.pack('<H',address)
        output[offset:offset+8] = b'\xCD'+struct.pack('<H',target)+bytes.fromhex('3E 01 C3')+struct.pack('<H',switch)


def fix_checksums(output):
    output[0x14D]=(-sum(output[0x134:0x14D])-25)&255
    output[0x14E:0x150]=b'\0\0'
    output[0x14E:0x150]=(sum(output)&65535).to_bytes(2,'big')


def patch_sprite_rectangle_bank_call(data, output, switch, native=False):
    # RenderActiveEntitySpritesRect used a temporary hardware-only bank-15
    # switch. A native LCD IRQ could restore another bank mid-render (DMG
    # intro). Save the caller bank on the stack and use ROM0 SwitchBank for
    # BOTH entry and return. All callers retain their original bank.
    #
    # Move the existing inactive-variant return beside the variant test. This
    # frees five bytes at the old tail. Compute DE=C030+slot directly (valid
    # slots are 00..5F), preserving input HL without the old push/add/pop.
    # The all-OAM entry still bypasses the variant test and starts at C000.
    prefix = bytes.fromhex('E5 21 00 C0 18 10 F0 F1 3C 28 67 E5 FA C0 C3 5F 16 00 21 30 C0 19 5D 54 E1')
    start, tail_at, target, reload = ((0x3CD7,0x3D3E,0x795F,0x0818) if native else
                                     (0x3CE0,0x3D47,0x795D,0x081D))
    tail = bytes.fromhex('3E 15 EA 00 21 CD') + struct.pack('<H',target) + b'\xC3' + struct.pack('<H',reload) + bytes.fromhex('FA 23 C1 4F C9')
    if data[start:start+25] != prefix or data[tail_at:tail_at+16] != tail:
        raise ValueError('Large-sprite renderer is modified or unsupported.')
    output[start:start+6] = bytes.fromhex('11 00 C0 C3')+struct.pack('<H',start+25)
    output[start+6:start+25] = bytes.fromhex('F0 F1 3C 20 05 FA 23 C1 4F C9 FA C0 C3 C6 30 5F 16 C0 00')
    output[tail_at:tail_at+16] = (bytes.fromhex('FA AF DB F5 3E 15 CD')+struct.pack('<H',switch)+
        b'\xCD'+struct.pack('<H',target)+bytes.fromhex('F1 C3')+struct.pack('<H',switch))


def patch(data):
    if data[MARKER:MARKER+8] == MAGIC:
        raise ValueError('HUD on Top is already installed. Use a pre-HUD ROM; old private prototypes are not upgrade inputs.')
    if (len(data) not in (0x100000,0x200000) or data[0x134:0x139]!=b'ZELDA' or
        data[0x147]!=0x1B or data[0x143] not in (0x80,0xC0)):
        raise ValueError('Select a 1 MiB or 2 MiB Link\'s Awakening DX ROM.')
    native = data[0x13F:0x143] == b'AZLE' and data[0x14C] == 2
    if not native:
        from hashlib import sha256
        if (data[0x13F:0x143] != bytes(4) or data[0x14C] != 0 or
            sha256(data[0x2300:0x2800]).hexdigest() != '4a28b2f572d2297c19f6e883f1b4d35bc1e717e33cdb157999be68002ef6a8d8' or
            sha256(data[0x7F10:0x7F92]).hexdigest() != 'c91ceb4d5789b19a8faeb4541abf94eec2fa4da77424371b6bfddf3eb570d930'):
            raise ValueError('Expected native English Rev2 or the researched original VWF layout.')
    is_native = native
    original_lcd=int.from_bytes(data[0x49:0x4B],'little')
    if data[0x48]!=0xC3 or not 0x300<=original_lcd<0x450:
        raise ValueError('LCD interrupt vector is modified or unsupported.')
    wy=unique(data,bytes.fromhex('FA 9A DB E0 4A'),0x200,0x380)
    vb=unique(data,bytes.fromhex('FB C1 79 E0 70 E1 D1 C1'),0x500,0x600)
    vblank_original=int.from_bytes(data[0x41:0x43],'little')
    if data[0x40]!=0xC3 or data[vblank_original:vblank_original+4]!=bytes.fromhex('F5 C5 D5 E5'):
        raise ValueError('VBlank entry is modified or unsupported.')
    begin=unique(data,bytes.fromhex('3E 01 E0 FD FA 00 C5'),0x150,0x200)
    frame_end=unique(data,bytes.fromhex('AF E0 FD 76 00 F0 D1'),0x350,0x380)
    end_site=frame_end-3
    if data[end_site]!=0xCD:raise ValueError('Frame-end hook is unsupported.')
    switch=int.from_bytes(data[end_site+1:end_site+3],'little')
    if data[original_lcd:original_lcd+5]!=bytes.fromhex('F3 F5 E5 D5 C5'):
        raise ValueError('LCD handler is modified or unsupported.')
    link_site=unique(data,bytes.fromhex('FA 3B C1 4F FA 45 C1'),0x1D00,0x1E00)
    native_end=unique(data,bytes.fromhex('79 E0 70 C1 D1 E1 F1 FB D9'),original_lcd,original_lcd+0x100)+9
    native=bytearray(data[original_lcd:native_end])
    if len(native)!=128:raise ValueError('Native LCD handler layout is unsupported.')
    # Last 137 bytes of the original 1 MiB image: bank 3F, CPU 7F77..7FFF.
    # Verified as unused trailing space in the supported Rev 2 disassembly.
    # Require known zero padding, including the 32-byte version header.
    bank, native_address, native_offset = 0x3F, 0x7F77, 0xFFF77
    if data[MARKER:0x100000] != bytes(169):
        raise ValueError('The final 169 bytes (HUD version header and native handler) are occupied. No output written.')
    intro_tables=data[original_lcd-9:original_lcd]
    if intro_tables!=bytes.fromhex('20 30 40 60 00 30 56 68 00'):
        raise ValueError('Intro scroll-table layout is unsupported.')
    routines=assemble(original_lcd,bank,native_address);symbols,regions=allocate(routines,(original_lcd-9,native_end),native=is_native)
    symbols['switch']=switch
    symbols['vblank_original']=vblank_original+1
    symbols['draw_link']=unique(data,bytes.fromhex('F0 9D 3C C8 F0 FE A7'),0x1D00,0x1D50)
    load_site=unique(data,bytes.fromhex('F3 CD'),0x220,0x240)+1
    if data[load_site+3]!=0xFB:raise ValueError('Graphics loader interrupt wrapper is unsupported.')
    symbols['load_original']=int.from_bytes(data[load_site+1:load_site+3],'little')
    unused_stubs={
        (0x3970,0x397B):bytes.fromhex('3E 03 EA 00 21 CD FE 7E C3 1D 08'),
        (0x3E29,0x3E34):bytes.fromhex('21 00 21 36 04 CD 63 5C C3 1D 08'),
    }
    if is_native:
        unused_stubs = {
            (0x3967,0x3972):bytes.fromhex('3E 03 EA 00 21 CD F7 7E C3 18 08'),
            (0x3E20,0x3E2B):bytes.fromhex('21 00 21 36 04 CD 63 5C C3 18 08'),
        }
    for a,b in regions:
        if (a,b) in unused_stubs:
            if data[a:b]!=unused_stubs[(a,b)]:
                raise ValueError('Unused trampoline layout is modified or unsupported.')
            # This trampoline is marked unused in the disassembly; reject direct callers
            # in a modified project ROM rather than replacing a live entry.
            for opcode in (0xCD,0xC3,0xC2,0xCA,0xD2,0xDA):
                if bytes([opcode])+struct.pack('<H',a) in data:
                    raise ValueError('Unused trampoline has a caller. No output written.')
            continue
        if (a,b)==(original_lcd-9,native_end):continue
        if any(data[a:b]):raise ValueError(f'Reserved ROM space {a:04X}–{b-1:04X} is occupied. No output written.')
    output=bytearray(data)
    output[0x148]=5 if len(output)==0x100000 else 6
    for name,code in routines.items():
        at=symbols[name];raw=code.resolve(at,symbols);output[at:at+len(raw)]=raw
    def call(at,name,size=3):output[at:at+size]=b'\xCD'+struct.pack('<H',symbols[name])+bytes(size-3)
    room_site=unique(data,bytes.fromhex('3E 01 E0 FF 21 7F D4'),0x3000,0x3200)
    call(room_site,'room',4)
    # All audited writes from wLCDControl: shared loader, inventory exit,
    # ending/cutscene and bank-36 graphics paths. Home routine is bank-safe.
    enable_sites=((0x461,0x5DAC5,0x81D58,0x81D64,0x82684,0xD81C1,0xD83B0,0xD8AB9) if is_native else
                  (0x464,0x5DB09,0x81D4C,0x81D58,0x8267C,0xD81C1,0xD83B0,0xD8AB9))
    for enable_site in enable_sites:
        if data[enable_site:enable_site+5]!=bytes.fromhex('FA FD D6 E0 40'):
            raise ValueError('LCD restart path is modified or unsupported.')
        call(enable_site,'enable',5)
    scroll_site=unique(data,bytes.fromhex('E0 42 F0 96'),0x1D0,0x210)
    call(scroll_site,'scroll',4)
    call(wy,'setup',5);call(load_site,'load')
    output[0x40:0x43]=b'\xC3'+struct.pack('<H',symbols['prime'])
    call(link_site,'link');call(begin,'begin',4);call(end_site,'end')
    # Link's existing clipping comparison now sees the added screen-space offset.
    clip=link_site+8
    if data[clip:clip+3]!=bytes.fromhex('FE 88 D0'):raise ValueError('Link clipping hook is unsupported.')
    output[clip+1]=0x98
    output[0x48:0x4B]=b'\xC3'+struct.pack('<H',symbols['lcd'])
    # Native handler's absolute internal jumps follow its relocation; its
    # terminal restore jumps home BEFORE restoring WRAM/registers, so the
    # saved ROM-bank variable is still read from WRAM bank 1.
    for i in range(len(native)-2):
        if native[i]==0xC3:
            target=int.from_bytes(native[i+1:i+3],'little')
            if original_lcd<=target<native_end:
                native[i+1:i+3]=struct.pack('<H',native_address+target-original_lcd)
    native[-9:-6]=b'\xC3'+struct.pack('<H',symbols['restore'])
    # The native handler is the sole reader of these two intro tables.
    # Move them with it, freeing nine additional always-visible ROM bytes.
    for old_offset,new_offset in ((-9,0),(-4,5)):
        pattern=b'\x21'+struct.pack('<H',original_lcd+old_offset)
        at=unique(native,pattern,0,len(native))
        native[at+1:at+3]=struct.pack('<H',native_address+len(native)+new_offset)
    relocated=native+intro_tables
    output[native_offset:native_offset+len(relocated)]=relocated
    patch_sprite_rectangle_bank_call(data, output, switch, native=is_native)
    patch_intro_palette_calls(data, output, switch, native=is_native)
    patch_inventory_palette_copies(data, output)
    patch_map_save_palette_copies(data, output, symbols['map_leave'], native=is_native)
    # Detectable, versioned data header immediately before the relocated code.
    # magic[8], version[3], format[1], header size[2], CPU address[2],
    # payload size[2], bank[1], flags[1], payload CRC32[4], prerelease label[8] (ASCII, zero-padded).
    header = MAGIC + bytes(VERSION) + bytes([1])
    header += struct.pack('<HHHBBI',32,native_address,len(relocated),bank,0,zlib.crc32(relocated))
    output[MARKER:native_offset] = header + PRERELEASE.ljust(8, b"\0")
    # A STAT wake must return to HALT until a fresh VBlank acknowledgement.
    # Clearing the acknowledgement before sleep prevents stale VBlank state
    # from advancing logic and overwriting a pending room graphics row.
    old_wait = bytes.fromhex('AF E0 FD 76 00 F0 D1 A7 28 FB AF E0 D1 C3 DA 01')
    if data[frame_end:frame_end+len(old_wait)] != old_wait:
        raise ValueError('Frame wait loop is modified or unsupported.')
    output[frame_end:frame_end+len(old_wait)] = bytes.fromhex('AF E0 FD E0 D1 76 00 F0 D1 A7 28 F9 C3 DA 01 00')
    # The main-loop LCDC shadow sync can run during scanline 0 while the
    # instrument's palette animation is active. Re-enabling OBJ there leaks
    # a few sprite pixels into the HUD until the later setup call disables it.
    # Keep the native shadow merge, but apply the current viewport mask BEFORE
    # the hardware write. The ROM0 caller uses the normal tracked bank switch;
    # both its return address and bank restoration execute in ROM0.
    sync_at = unique(data,bytes.fromhex('FA FD D6 E6 7F 5F F0 40 E6 80 B3 E0 40 21 E7 FF'),0x230,0x260)
    sync_original = bytes.fromhex('FA FD D6 E6 7F 5F F0 40 E6 80 B3 E0 40 21 E7 FF')
    if data[sync_at:sync_at+16] != sync_original:
        raise ValueError('Main-loop LCDC shadow sync is modified or unsupported.')
    helper_at, helper_cpu = 0xFFF00, 0x7F00
    if any(data[helper_at:MARKER]):
        raise ValueError('VWF HUD shadow-sync helper space is occupied.')
    helper = (Code().emit('FA FD D6 E6 7F 5F F0 40 E6 80 B3 F5')
        .address('CD','guard').branch('20','plain')
        .emit('F0 44 C6 70 E6 80').branch('20','world')
        .emit('F1 E6 FD F6 20').branch('18','write')
        .label('world').emit('F1 E6 DF F6 02').branch('18','write')
        .label('plain').emit('F1').label('write').emit('E0 40 21 E7 FF C9'))
    raw = helper.resolve(helper_cpu,symbols)
    if helper_at+len(raw)>MARKER:
        raise ValueError('VWF HUD shadow-sync helper exceeds reserved space.')
    output[helper_at:helper_at+len(raw)] = raw
    output[sync_at:sync_at+16] = (bytes.fromhex('FA AF DB F5 3E 3F CD')+
        struct.pack('<H',switch)+b'\xCD'+struct.pack('<H',helper_cpu)+
        b'\xF1\xCD'+struct.pack('<H',switch))
    # A and flags are dead here: the next INC updates frame count, then LD/CP
    # starts the gameplay dispatch. E, HL, bank selection and stack match it.
    # Nintendo header checksum and global ROM checksum.
    fix_checksums(output)
    return bytes(output)


def make_ips(before, after):
    """Fixed-layout IPS output for the selected input; no ROM expansion."""
    result=bytearray(b'PATCH');i=0
    while i<len(after):
        if before[i]==after[i]:i+=1;continue
        start=i
        while i<len(after) and before[i]!=after[i] and i-start<0xFFFF:i+=1
        result.extend(start.to_bytes(3,'big'));result.extend((i-start).to_bytes(2,'big'));result.extend(after[start:i])
    return bytes(result)+b'EOF'


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom',nargs='?',type=Path)
    parser.add_argument('--output',type=Path,help='New output ROM; existing files are never overwritten.')
    args=parser.parse_args();gui=args.rom is None
    if gui:
        import tkinter as tk
        from tkinter import filedialog,messagebox
        root=tk.Tk();root.withdraw()
        selected=filedialog.askopenfilename(title='Choose native Rev2 or original VWF ROM',
            filetypes=[('Game Boy ROM','*.gbc *.gb'),('All files','*.*')])
        if not selected:root.destroy();return
        args.rom=Path(selected)
    try:
        before=args.rom.read_bytes();after=patch(before)
        target=args.output or args.rom.with_name(args.rom.stem+'-hud-on-top-'+RELEASE+args.rom.suffix)
        ips=target.with_suffix('.ips')
        if target.resolve()==args.rom.resolve() or ips.resolve()==args.rom.resolve():
            raise ValueError('Choose a new output filename.')
        if target.exists() or ips.exists():raise FileExistsError('An output file already exists. Choose a new output filename.')
        for path,raw in ((target,after),(ips,make_ips(before,after))):
            with path.open('xb') as output:output.write(raw)
        message=f'Created {target}\nCreated {ips}\nOriginal preserved. ROM size unchanged.'
        print(message)
        if gui:messagebox.showinfo('HUD on Top',message,parent=root)
    except (OSError,ValueError) as exc:
        if gui:messagebox.showerror('Cannot patch ROM',str(exc),parent=root)
        else:raise SystemExit(str(exc))
    finally:
        if gui:root.destroy()


if __name__=='__main__':main()
