default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000  ; IEEE 754 符号位掩码

section .text
global kfn_main

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    push 10
    pop rax
    mov [rbp - 8], rax
    push 20
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
    push 30
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

