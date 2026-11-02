.section .grain_rows,"aw"
.balign 4
.global grain_rows
grain_rows:
 .zero 180

.section .text,"ax"
.macro diagnostic_save
 movm [d2,d3,a2,a3,other],(sp)
 mov psw,d2
 add -4,sp
 mov d2,(4,sp)
 mov (48,sp),d2
.endm
.macro diagnostic_restore
 mov (4,sp),d2
 add 4,sp
 mov d2,psw
 movm (sp),[d2,d3,a2,a3,other]
.endm
.macro diagnostic_word register, value, offset
 diagnostic_save
 cmp \value,\register
 bne 991f
 mov 1,d3
 movbu d3,(grain_diagnostic_uncached+\offset)
991:
 diagnostic_restore
.endm
.global grain_decode,grain_select,grain_queue,grain_combiner
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
 diagnostic_word d0,3,2
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
 diagnostic_save
 movbu (1088,a2),d3
 cmp 3,d3
 bne 1f
 mov 1,d3
 movbu d3,(grain_diagnostic_uncached+3)
1:
 diagnostic_restore
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
 diagnostic_save
 cmp 2,d0
 bne 1f
 movhu (12,a0),d3
 cmp 0x901,d3
 beq 2f
 cmp 0x902,d3
 bne 1f
2:
 mov 1,d3
 movbu d3,(grain_diagnostic_uncached+4)
1:
 diagnostic_restore
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
 diagnostic_word d0,0xf7524e03,0
 mov a2,a0
 mov d2,d0
 add 4,sp
 movm (sp),[d2,a2]
 ret [],4

grain_to_job:
 cmp 0,a0
 beq grain_job_invalid
 mov a0,d0
 cmp tone_compact_rows,d0
 bcc grain_job_copy
 mov a2,a1
 add -14920,a1
 mov (4,a1),d0
 cmp 0x6051fbcc,d0
 bne grain_job_copy
 mov (12192,a1),d0
 cmp 11,d0
 bne grain_job_copy
 mov (40,a2),d0
 and 0xfffffffc,d0
 cmp 0xf7524e00,d0
 beq grain_job_preserved
grain_job_copy:
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
 diagnostic_word d0,0xf7524e03,1
grain_job_preserved:
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

.section .grain_constructor_gate,"ax"
.global grain_constructor_gate,grain_prepare_gate
grain_constructor_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 beq 1f
 jmp grain_constructor_loaded
1:
 call grain_native_604c2a4f,[d2,a2,a3],16
 jmp grain_native_604c2032

.section .grain_select_gate,"ax"
grain_prepare_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 beq 1f
 jmp grain_prepare_loaded
1:
 call grain_native_604be99a,[d2,a2],12
 jmp grain_native_604c20d7

.section .text,"ax"
grain_constructor_loaded:
 diagnostic_save
 call grain_constructor_snapshot,[],4
 diagnostic_restore
 call grain_native_604c2a4f,[d2,a2,a3],16
 jmp grain_native_604c2032
grain_prepare_loaded:
 diagnostic_save
 call grain_prepare_strength,[],4
 diagnostic_restore
 call grain_native_604be99a,[d2,a2],12
 jmp grain_native_604c20d7

.section .text,"ax"
grain_constructor_snapshot:
 clr d0
 mov d0,(14960,a3)
 mov (4,a3),d0
 cmp 0x6051fbcc,d0
 bne grain_constructor_done
 mov (12192,a3),d0
 cmp 11,d0
 bne grain_constructor_done
 mov (8,a3),a0
 mov a0,d0
 sub 0xa1c67cb4,d0
 cmp 180,d0
 bcc grain_constructor_done
 mov 20,d1
 clr d2
 mov d2,mdr
 divu d1,d0
 mov mdr,d1
 cmp 0,d1
 bne grain_constructor_done
 movbu (12,a0),d0
 cmp 1,d0
 bne grain_constructor_done
 mov (8,a0),d0
 cmp 1,d0
 bcs grain_constructor_done
 cmp 41,d0
 bcc grain_constructor_done
 mov d0,d1
 asl 2,d1
 add d0,d1
 asl 2,d1
 mov 0x618689b8,a0
 add d1,a0
 movhu (a0),d1
 btst 4,d1
 beq grain_constructor_done
 call grain_native_60249c22,[],20
 call hl_owner_row,[],4
 call tone_hl_row,[],4
 mov a3,a2
 add 14920,a2
 call grain_to_job,[],4
grain_constructor_done:
 ret [],4

grain_prepare_strength:
 mov a0,a3
 mov (12192,a3),d0
 cmp 11,d0
 bne grain_prepare_done
 mov (14960,a3),d0
 call grain_decode,[],4
 movbu d0,(5733,a3)
grain_prepare_done:
 ret [],4
