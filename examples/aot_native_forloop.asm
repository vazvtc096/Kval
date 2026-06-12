default rel
extern printf

section .data
    fmt_int db "%d", 10, 0
    sign_mask dq 0x8000000000000000

section .text
global kfn_sum_range
global kfn_main

kfn_sum_range:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov [rbp - 8], rcx
    push 0
    pop rax
    mov [rbp - 16], rax
    push 1
    pop rax
    mov [rbp - 24], rax
kfn__46_forcond1:
    push qword [rbp - 24]
    push qword [rbp - 8]
    pop rbx
    pop rax
    cmp rax, rbx
    setle al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor2
    push qword [rbp - 16]
    push qword [rbp - 24]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 16], rax
kfn__46_forstep3:
    push qword [rbp - 24]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 24], rax
    jmp kfn__46_forcond1
kfn__46_endfor2:
    push qword [rbp - 16]
    pop rax
    leave
    ret

kfn_main:
    push rbp
    mov rbp, rsp
    sub rsp, 48
    push 10
    pop rax
    mov [rbp - 8], rax
    push qword [rbp - 8]
    pop rcx
    sub rsp, 32
    call kfn_sum_range
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
    push 0
    pop rax
    mov [rbp - 24], rax
    push 1
    pop rax
    mov [rbp - 32], rax
kfn__46_forcond4:
    push qword [rbp - 32]
    push 10
    pop rbx
    pop rax
    cmp rax, rbx
    setle al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor5
    push qword [rbp - 32]
    push 5
    pop rbx
    pop rax
    cmp rax, rbx
    setg al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif7
    jmp kfn__46_endfor5
kfn__46_endif7:
    push qword [rbp - 24]
    push qword [rbp - 32]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 24], rax
kfn__46_forstep6:
    push qword [rbp - 32]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 32], rax
    jmp kfn__46_forcond4
kfn__46_endfor5:
    push qword [rbp - 24]
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
    mov [rbp - 40], rax
    push 1
    pop rax
    mov [rbp - 48], rax
kfn__46_forcond8:
    push qword [rbp - 48]
    push 10
    pop rbx
    pop rax
    cmp rax, rbx
    setle al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endfor9
    push qword [rbp - 48]
    push 2
    pop rbx
    pop rax
    cqo
    idiv rbx
    push rdx
    push 0
    pop rbx
    pop rax
    cmp rax, rbx
    sete al
    movzx eax, al
    push rax
    pop rax
    test rax, rax
    jz kfn__46_endif11
    jmp kfn__46_forstep10
kfn__46_endif11:
    push qword [rbp - 40]
    push qword [rbp - 48]
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 40], rax
kfn__46_forstep10:
    push qword [rbp - 48]
    push 1
    pop rbx
    pop rax
    add rax, rbx
    push rax
    pop rax
    mov [rbp - 48], rax
    jmp kfn__46_forcond8
kfn__46_endfor9:
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

