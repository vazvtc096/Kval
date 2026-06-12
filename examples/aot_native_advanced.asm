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
    sub rsp, 32
    mov rax, 4613937818241073152
    push rax  ; float 3.0
    pop rax
    mov [rbp - 8], rax
    mov rax, 4611686018427387904
    push rax  ; float 2.0
    pop rax
    mov [rbp - 16], rax
    push 1
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 2
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 3
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
    push 10
    pop rbx
    pop rax
    add rax, rbx
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

