default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_add
global kfn_main

kfn_add:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov [rbp - 8], rcx
    mov [rbp - 16], rdx
    push qword [rbp - 8]
    push qword [rbp - 16]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    leave
    ret

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 64
    push 10
    pop rax
    mov [rbp - 8], rax
    push 32
    pop rax
    mov [rbp - 16], rax
    push qword [rbp - 8]
    push qword [rbp - 16]
    pop rdx
    pop rcx
    sub rsp, 32
    call kfn_add
    add rsp, 32
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
    push qword [rbp - 16]
    push qword [rbp - 8]
    pop rbx
    pop rax
    sub rax, rbx
    push rax
    pop rax
    mov [rbp - 32], rax
    push qword [rbp - 32]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push qword [rbp - 8]
    push 3
    pop rbx
    pop rax
    imul rax, rbx
    push rax
    pop rax
    mov [rbp - 40], rax
    push qword [rbp - 40]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push qword [rbp - 16]
    push 2
    pop rbx
    pop rax
    cqo
    idiv rbx
    push rax
    pop rax
    mov [rbp - 48], rax
    push qword [rbp - 48]
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push qword [rbp - 16]
    push 3
    pop rbx
    pop rax
    cqo
    idiv rbx
    push rdx
    pop rax
    mov [rbp - 56], rax
    push qword [rbp - 56]
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

