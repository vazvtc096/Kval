default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_compute
global kfn_main

kfn_compute:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov [rbp - 8], rcx
    push 0
    pop rax
    mov [rbp - 16], rax
    push 0
    pop rax
    mov [rbp - 24], rax
kfn__46_while1:
    push qword [rbp - 24]
    push qword [rbp - 8]
    pop rbx
    pop rax
    cmp rax, rbx
    setl al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endwhile2
    push qword [rbp - 16]
    push qword [rbp - 24]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 16], rax
    push qword [rbp - 24]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 24], rax
    jmp kfn__46_while1
kfn__46_endwhile2:
    push qword [rbp - 16]
    pop rax
    leave
    ret

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    push 10
    pop rax
    mov [rbp - 8], rax
    push qword [rbp - 8]
    pop rcx
    sub rsp, 32
    call kfn_compute
    add rsp, 32
    push rax
    pop rax
    mov [rbp - 16], rax
    push qword [rbp - 16]
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
    mov [rbp - 24], rax
    push qword [rbp - 24]
    push 40
    pop rbx
    pop rax
    cmp rax, rbx
    setg al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_else4
    push qword [rbp - 24]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    jmp kfn__46_endif3
kfn__46_else4:
    push 0
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
kfn__46_endif3:
    push 20
    pop rax
    mov [rbp - 32], rax
    push qword [rbp - 32]
    push 40
    pop rbx
    pop rax
    cmp rax, rbx
    setg al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_else6
    push qword [rbp - 32]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    jmp kfn__46_endif5
kfn__46_else6:
    push qword [rbp - 32]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
kfn__46_endif5:
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

