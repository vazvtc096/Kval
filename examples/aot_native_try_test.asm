default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_divide
global kfn_main

kfn_divide:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov [rbp - 8], rcx
    mov [rbp - 16], rdx
    push qword [rbp - 16]
    push 0
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif1
kfn__46_endif1:
    push qword [rbp - 8]
    push qword [rbp - 16]
    pop rbx
    pop rax
    cqo
    idiv rbx
    push rax
    pop rax
    leave
    ret

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    push 100
    push 5
    pop rdx
    pop rcx
    sub rsp, 32
    call kfn_divide
    add rsp, 32
    push rax
    pop rax
    mov [rbp - 8], rax
    push qword [rbp - 8]
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

