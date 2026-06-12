default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_factorial
global kfn_main

kfn_factorial:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov [rbp - 8], rcx
    push qword [rbp - 8]
    push 1
    pop rbx
    pop rax
    cmp rax, rbx
    setle al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif1
    push 1
    pop rax
    leave
    ret
kfn__46_endif1:
    push qword [rbp - 8]
    push qword [rbp - 8]
    push 1
    pop rbx
    pop rax
    sub rax, rbx
    push rax
    pop rcx
    sub rsp, 32
    call kfn_factorial
    add rsp, 32
    push rax
    pop rbx
    pop rax
    imul rax, rbx
    push rax
    pop rax
    leave
    ret

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    push 5
    pop rcx
    sub rsp, 32
    call kfn_factorial
    add rsp, 32
    push rax
    pop rdx
    sub rsp, 32
    lea rcx, [fmt_int]
    xor eax, eax
    call printf
    add rsp, 32
    push 0
    add rsp, 8
    push 10
    pop rcx
    sub rsp, 32
    call kfn_factorial
    add rsp, 32
    push rax
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

