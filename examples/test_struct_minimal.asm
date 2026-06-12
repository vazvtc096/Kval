default rel
extern printf
section .data
    fmt_int db "%d", 10, 0
section .text
global main
main:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    
    ; struct Point { int x; int y; } at rbp-16 (16 bytes)
    mov qword [rbp-16], 10   ; p.x = 10
    mov qword [rbp-8], 20    ; p.y = 20
    
    mov rax, [rbp-16]
    add rax, [rbp-8]
    mov [rbp-24], rax      ; sum = 30
    
    mov rdx, [rbp-24]
    lea rcx, [fmt_int]
    sub rsp, 32
    xor eax, eax
    call printf
    add rsp, 32
    
    xor eax, eax
    leave
    ret
