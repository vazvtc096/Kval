default rel
extern printf
extern malloc
extern free

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_main

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    ; malloc for struct p (size=16)
    sub rsp, 32
    mov ecx, 16
    call malloc
    add rsp, 32
    mov [rbp - 16], rax
    ; decl struct Point p (heap, size=16)
    mov rdi, [rbp - 16]
    xor eax, eax
    mov ecx, 2
    rep stosq
    push qword [rbp - 16]
    push 10
    pop rax
    pop rbx
    mov [rbx + 0], rax
    push 0  ; assign result
    add rsp, 8
    push qword [rbp - 16]
    push 20
    pop rax
    pop rbx
    mov [rbx + 8], rax
    push 0  ; assign result
    add rsp, 8
    push qword [rbp - 16]
    pop rbx
    mov rax, [rbx + 0]
    push rax
    push qword [rbp - 16]
    pop rbx
    mov rax, [rbx + 8]
    push rax
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
    ; RAII cleanup
    push rax              ; 保存返回值
    mov rcx, [rbp - 16]
    test rcx, rcx
    jz _skip_free_kfn_main_16
    sub rsp, 32
    call free
    add rsp, 32
_skip_free_kfn_main_16:
    pop rax               ; 恢复返回值
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

