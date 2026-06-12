default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_main

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 192
    push 42
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 10
    pop rax
    mov [rbp - 8], rax
    push 32
    pop rax
    mov [rbp - 16], rax
    push qword [rbp - 8]
    push qword [rbp - 16]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 24], rax
    push qword [rbp - 24]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push qword [rbp - 24]
    push 42
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_else2
    push 100
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    jmp kfn__46_endif1
kfn__46_else2:
    push 0
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
kfn__46_endif1:
    push 0
    pop rax
    mov [rbp - 32], rax
    push 0
    pop rax
    mov [rbp - 40], rax
kfn__46_while3:
    push qword [rbp - 32]
    push 5
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endwhile4
    push qword [rbp - 40]
    push qword [rbp - 32]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 40], rax
    push qword [rbp - 32]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 32], rax
    jmp kfn__46_while3
kfn__46_endwhile4:
    push qword [rbp - 40]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    mov [rbp - 48], rax
    push 0
    pop rax
    mov [rbp - 56], rax
kfn__46_forcond5:
    push qword [rbp - 56]
    push 5
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor6
    push qword [rbp - 48]
    push qword [rbp - 56]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 48], rax
kfn__46_forstep7:
    push qword [rbp - 56]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 56], rax
    jmp kfn__46_forcond5
kfn__46_endfor6:
    push qword [rbp - 48]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    mov [rbp - 64], rax
    push 0
    pop rax
    mov [rbp - 72], rax
kfn__46_forcond8:
    push qword [rbp - 72]
    push 3
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor9
    push 0
    pop rax
    mov [rbp - 80], rax
    push 0
    pop rax
    mov [rbp - 88], rax
kfn__46_forcond11:
    push qword [rbp - 88]
    push 2
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor12
    push qword [rbp - 80]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 80], rax
kfn__46_forstep13:
    push qword [rbp - 88]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 88], rax
    jmp kfn__46_forcond11
kfn__46_endfor12:
    push qword [rbp - 64]
    push qword [rbp - 80]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 64], rax
kfn__46_forstep10:
    push qword [rbp - 72]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 72], rax
    jmp kfn__46_forcond8
kfn__46_endfor9:
    push qword [rbp - 64]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    mov [rbp - 96], rax
    push 0
    pop rax
    mov [rbp - 104], rax
kfn__46_forcond14:
    push qword [rbp - 104]
    push 6
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor15
    push qword [rbp - 96]
    push qword [rbp - 104]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 96], rax
kfn__46_forstep16:
    push qword [rbp - 104]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 104], rax
    jmp kfn__46_forcond14
kfn__46_endfor15:
    push qword [rbp - 96]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    mov [rbp - 112], rax
    push 0
    pop rax
    mov [rbp - 120], rax
kfn__46_forcond17:
    push qword [rbp - 120]
    push 10
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor18
    push qword [rbp - 120]
    push 5
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif20
    jmp kfn__46_endfor18
kfn__46_endif20:
    push qword [rbp - 120]
    push 2
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif21
    jmp kfn__46_forstep19
kfn__46_endif21:
    push qword [rbp - 112]
    push qword [rbp - 120]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 112], rax
kfn__46_forstep19:
    push qword [rbp - 120]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 120], rax
    jmp kfn__46_forcond17
kfn__46_endfor18:
    push qword [rbp - 112]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 1
    pop rax
    mov [rbp - 128], rax
    push 0
    pop rax
    mov [rbp - 136], rax
    push 0
    pop rax
    mov [rbp - 144], rax
    push qword [rbp - 128]
    push 1
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif22
    push qword [rbp - 136]
    push 0
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif23
    push 10
    pop rax
    mov [rbp - 144], rax
kfn__46_endif23:
kfn__46_endif22:
    push qword [rbp - 144]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    mov [rbp - 152], rax
    push qword [rbp - 128]
    push 1
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif24
    push 20
    pop rax
    mov [rbp - 152], rax
kfn__46_endif24:
    push qword [rbp - 152]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 42
    pop rax
    mov [rbp - 160], rax
    push qword [rbp - 160]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    mov [rbp - 168], rax
    push 1
    pop rax
    test rax, rax
    jz kfn__46_endif25
    push 1
    pop rax
    mov [rbp - 168], rax
kfn__46_endif25:
    push 1
    pop rax
    test rax, rax
    jz kfn__46_endif26
    push qword [rbp - 168]
    push 2
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 168], rax
kfn__46_endif26:
    push 1
    pop rax
    test rax, rax
    jz kfn__46_endif27
    push qword [rbp - 168]
    push 4
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 168], rax
kfn__46_endif27:
    push 1
    pop rax
    test rax, rax
    jz kfn__46_endif28
    push qword [rbp - 168]
    push 8
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 168], rax
kfn__46_endif28:
    push 1
    pop rax
    test rax, rax
    jz kfn__46_endif29
    push qword [rbp - 168]
    push 16
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 168], rax
kfn__46_endif29:
    push 1
    pop rax
    test rax, rax
    jz kfn__46_endif30
    push qword [rbp - 168]
    push 32
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 168], rax
kfn__46_endif30:
    push qword [rbp - 168]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 6
    pop rax
    mov [rbp - 176], rax
    push 3
    pop rax
    mov [rbp - 184], rax
    push qword [rbp - 176]
    push qword [rbp - 184]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 192], rax
    push qword [rbp - 192]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 0
    pop rax
    leave
    ret

global main
main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    call kfn_main
    leave
    ret

