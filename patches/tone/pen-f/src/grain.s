.section .grain_rows,"aw"
.balign 4
.global grain_rows
grain_rows:
 .zero 180

.section .text,"ax"
.global grain_decode,grain_select,grain_queue,grain_job_unloaded,grain_combiner
grain_decode:
 mov d0,d1
 and 0xfffffffc,d1
 cmp 0xf7524e00,d1
 bne grain_invalid
 and 3,d0
 ret [],4
grain_invalid:
 clr d0
 ret [],4

grain_select:
 mov (12192,a0),d1
 cmp 11,d1
 bne grain_select_stock
 mov (14960,a0),d0
 call grain_decode,[],4
 movbu d0,(5733,a0)
 cmp 0,d0
 beq grain_select_color
 jmp grain_native_604c5c46
grain_select_color:
 mov 11,d1
grain_select_stock:
 cmp 12,d1
 bcc grain_select_higher
 jmp grain_native_604c5d33
grain_select_higher:
 jmp grain_native_604c58a7

grain_queue:
 mov a0,a2
 add 12228,a2
 cmp 0,a1
 beq grain_queue_request
 mov a1,a2
grain_queue_request:
 movbu (16,a2),d2
 cmp 0,d2
 bne grain_queue_stock
 movhu (10,a2),d2
 cmp 11,d2
 bne grain_queue_stock
 movhu (12,a2),d2
 cmp 2304,d2
 bne grain_queue_stock
 movbu (1088,a2),d2
 add -1,d2
 cmp 3,d2
 bcc grain_queue_stock
 mov 12,d2
 movhu d2,(10,a2)
grain_queue_stock:
 jmp grain_native_604c2f1d

grain_combiner:
 cmp 11,d0
 bne grain_combiner_stock
 mov (a2),a0
 movbu (16,a0),d0
 cmp 0,d0
 bne grain_combiner_color
 movbu (1088,a0),d0
 add -1,d0
 cmp 3,d0
 bcc grain_combiner_color
 jmp grain_native_604fb918
grain_combiner_color:
 mov 11,d0
grain_combiner_stock:
 cmp 12,d0
 beq grain_combiner_mono
 jmp grain_native_604fb887
grain_combiner_mono:
 jmp grain_native_604fb918

.section .text,"ax"
.global grain_acquire,grain_to_job,grain_clear
grain_acquire:
 movm [d2,a2],(sp)
 add -4,sp
 mov d0,d2
 mov a0,a2
 cmp 3,d0
 bcc grain_acquire_off
 asl 2,d0
 mov grain_source_uncached,a0
 mov (d0,a0),d0
 bra grain_acquire_store
grain_acquire_off:
 clr d0
grain_acquire_store:
 mov a1,d1
 sub tone_rows_uncached,d1
 lsr 2,d1
 mov grain_rows_uncached,a0
 mov d0,(d1,a0)
 mov a2,a0
 mov d2,d0
 add 4,sp
 movm (sp),[d2,a2]
 ret [],4

grain_to_job:
 cmp 0,a0
 beq grain_job_invalid
 mov a0,d0
 sub tone_rows_uncached,d0
 lsr 2,d0
 mov grain_rows_uncached,a1
 mov (d0,a1),d0
 bra grain_job_store
grain_job_invalid:
 clr d0
grain_job_store:
 mov d0,(40,a2)
 ret [],4

grain_clear:
 cmp 0,a0
 beq grain_clear_done
 mov a0,d0
 sub tone_rows_uncached,d0
 lsr 2,d0
 mov grain_rows_uncached,a1
 clr d1
 mov d1,(d0,a1)
grain_clear_done:
 ret [],4

.section .grain_select_gate,"ax"
.global grain_select_gate,grain_combiner_gate,grain_queue_gate
grain_select_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 beq grain_select_unloaded
 jmp grain_select
grain_select_unloaded:
 mov (12192,a0),d1
 cmp 12,d1
 bcc grain_select_native_higher
 jmp grain_native_604c5d33
grain_select_native_higher:
 jmp grain_native_604c58a7
grain_job_unloaded:
 clr d0
 .irp offset,24,28,32,36,40
 mov d0,(\offset,a2)
 .endr
 ret [],4


.section .grain_combiner_gate,"ax"
grain_combiner_gate:
 movbu (0xa1c58404),d1
 btst 128,d1
 beq grain_combiner_unloaded
 jmp grain_combiner
grain_combiner_unloaded:
 cmp 12,d0
 beq grain_combiner_native_mono
 jmp grain_native_604fb887
grain_combiner_native_mono:
 jmp grain_native_604fb918
.section .grain_queue_gate,"ax"
grain_queue_gate:
 movbu (0xa1c58404),d2
 btst 128,d2
 beq grain_queue_unloaded
 jmp grain_queue
grain_queue_unloaded:
 jmp grain_native_604c2f1d

.section .grain_primary_gate,"ax"
.global grain_primary_gate
grain_primary_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 bne grain_primary_loaded
 jmp grain_primary_native
grain_primary_loaded:
 jmp grain_primary_call
.section .grain_combiner_gate,"ax"
grain_primary_native:
 call grain_native_604c4b3f,[d2,d3,a2,a3],20
 jmp grain_native_604c5435
.global grain_resident_end
grain_resident_end:
.section .text,"ax"
grain_primary_call:
 call grain_primary,[d2,d3,a2,a3],20
 jmp grain_native_604c5435
grain_primary:
 add -8,sp
 mov a0,(4,sp)
 call grain_native_604c4b3f,[d2,d3,a2,a3],20
 mov d0,d3
 mov (4,sp),a2
 mov (12192,a2),d0
 cmp 11,d0
 bne grain_primary_done
 mov (14960,a2),d0
 call grain_decode,[],4
 cmp 0,d0
 beq grain_primary_done
 clr d3
grain_primary_done:
 mov d3,d0
 add 8,sp
 ret [d2,d3,a2,a3],20
