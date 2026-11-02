`default_nettype wire
/* verilator lint_off IMPORTSTAR */
import tinytracer_pkg::*;
/* verilator lint_on IMPORTSTAR */

// Debug export intermediate for FSM
/* verilator lint_off DECLFILENAME */ // debug build only: package sits beside the module
package iu_types_pkg;
    typedef enum logic [1:0] {
        S_IDLE       = 2'd0,
        S_RTU_LOAD   = 2'd1,
        S_PROCESS_BV = 2'd2,
        S_CHECKOUT   = 2'd3
    } state_t;

    typedef enum logic [1:0] {
        S_SRAM_IDLE = 2'd0,
        S_SRAM_SEND = 2'd1,
        S_SRAM_WAIT = 2'd2,
        S_SRAM_NEXT = 2'd3
    } sram_state_t;

    typedef enum logic [1:0] {
        S_DEC_IDLE = 2'd0,
        S_DEC_SEND = 2'd1,
        S_DEC_WAIT = 2'd2,
        S_DEC_DONE = 2'd3
    } dec_state_t;
    
    // WiP not implemented
    // p = ray * t
    // outward_normal = (p - bv_origin) / bv_r
    // front_face = (dot(ray_dir, normal) < 0)
    // normal = front_face ? outward_normal : -outward_normal;
    // hit_flip =
    //
    // The old stages (CALC_A .. CALC_T) found the distance with the quadratic
    // t = (h + sqrt(h*h - a*c)) / a. A bounding-volume test needs no distance at
    // all and the sphere test only needs the half chord, so the sequence now
    // follows the spec's along/offset form, which the sphere test reuses as is:
    typedef enum logic [4:0] {
        CALC_R2     = 5'd0,   // r_s^2 = r_s x r_s                 M_MUL fmt 0       3
        CALC_TC     = 5'd1,   // to_centre = C - O                 M_VSUB            7
        CALC_ALONG  = 5'd2,   // along = to_centre . D             M_DOT fmt 1      11
        CALC_TCSQ   = 5'd3,   // |to_centre_s|^2                   M_DOT fmt 0      11  (u,v by K)
        CALC_INSIDE = 5'd4,   // |to_centre_s|^2 < r_s^2 ?         M_LT              3  yes: reach
        CALC_BEHIND = 5'd5,   // along < 0 ?                       M_LT              3  yes: skip
        CALC_M      = 5'd6,   // along x D                         M_SCAL_VEC fmt 1  7
        CALC_OFF    = 5'd7,   // offset = along x D - to_centre    M_VSUB            7
        CALC_OFFSQ  = 5'd8,   // |offset_s|^2                      M_DOT fmt 0      11  (u,v by K)
        CALC_REACH  = 5'd9,   // |offset_s|^2 < r_s^2 ?            M_LT              3  yes: reach
        // Sphere test (spec 5d). The first six steps are the same walk as the
        // BV test, so they reuse the same slots; only the radius and centre
        // come from the object record instead of the BV record.
        SP_R2       = 5'd10,  // r_s^2 = r_s x r_s                 M_MUL fmt 0       3
        SP_TC       = 5'd11,  // to_centre = C - O                 M_VSUB            7
        SP_ALONG    = 5'd12,  // along = to_centre . D             M_DOT fmt 1      11
        SP_M        = 5'd13,  // along x D                         M_SCAL_VEC fmt 1  7
        SP_OFF      = 5'd14,  // offset = along x D - to_centre    M_VSUB            7
        SP_OFFSQ    = 5'd15,  // |offset_s|^2                      M_DOT fmt 0      11  (u,v by K)
        SP_MISS     = 5'd16,  // |offset_s|^2 < r_s^2 ?            M_LT              3  no: miss
        SP_HALF2    = 5'd17,  // r_s^2 - |offset_s|^2              M_SUB             3
        SP_SQRT     = 5'd18,  // half_s = sqrt(r_s^2 - off_s^2)    M_SQRT fmt 0     25
        SP_T        = 5'd19,  // t = along - half                  M_SUB             3  entry point
        SP_TGATE    = 5'd20,  // 0.0156 < t ?                      M_LT              3  yes: candidate
        SP_T2       = 5'd21,  // t = along + half                  M_ADD             3  exit point, flip 1
        SP_TGATE2   = 5'd22,  // 0.0156 < t ?                      M_LT              3  no: miss
        SP_BEST     = 5'd23,  // t < best t ?                      M_LT              3  yes: keep
        CALC_DONE   = 5'd24   // this BV or this object is finished
        // WiP for hit_flip

    } calc_stage_t;

    // Phase: which memory read or step sequence is running. PH_READ is BV
    // w1-w4, PH_W0 is BV w0 (reach only), PH_OBJ is an object's w0 (type bit),
    // PH_HEAD its w3-w6, PH_SPHERE the sphere steps, the rest advance.
    typedef enum logic [2:0] {
        PH_READ     = 3'd0,
        PH_CALC     = 3'd1,
        PH_W0       = 3'd2,
        PH_NEXT     = 3'd3,
        PH_OBJ      = 3'd4,
        PH_HEAD     = 3'd5,
        PH_SPHERE   = 3'd6,
        PH_OBJ_NEXT = 3'd7
    } bv_phase_t;
endpackage
/* verilator lint_on DECLFILENAME */

/* verilator lint_off IMPORTSTAR */
import iu_types_pkg::*;
/* verilator lint_on IMPORTSTAR */

// Intersection Unit: finds the closest thing that one ray segment hits.
module intersection_unit #(
    /* verilator lint_off VARHIDDEN */ // names come from the package, redeclared per module
    parameter ADDR_WIDTH = 9,
    parameter WLEN       = 16,
    parameter DATA_WIDTH = 16
    /* verilator lint_on VARHIDDEN */
) (
    input  logic                   clk,
    input  logic                   rst_n,       // global reset, active low

    // RTU FSM <-> Intersection Unit
    input  logic                   start,       // 1-cycle pulse: search one segment
    output logic                   done,        // 1-cycle pulse: the hit outputs are valid
    output logic                   hit,         // 1 = object or ground hit, 0 = sky
    output logic                   hit_ground,  // 1 = the hit is the ground (only with hit = 1)
    output logic [WLEN-1:0]        hit_t,       // distance to the hit, POS (Q9.7)
    output logic [ADDR_WIDTH-1:0]  hit_addr,    // SRAM address of the hit object's w0
    output logic                   hit_flip,    // sphere: ray started inside; triangle: back side

    // Ray and scene, from RTU registers (must not change from start to done)
    input  logic [47:0]            ray_origin,  // O, POS (Q9.7): z [47:32], y [31:16], x [15:0]
    input  logic [47:0]            ray_dir,     // D, DIR (Q2.14), length 1: z [47:32], y [31:16], x [15:0]
    input  logic [4:0]             bv_count,    // number of BVs, 0 to 16 (header w15[7:3])

    // SRAM reads (the RTU passes them on to the SRAM Controller)
    output logic [ADDR_WIDTH-1:0]  sram_addr,   // register: address of the word to read
    output logic                   sram_rd,     // 1-cycle pulse: read the word at sram_addr
    input  logic [DATA_WIDTH-1:0]  sram_data,   // SRAM word, shared by all RTU sub-blocks
    input  logic                   sram_valid,  // 1 = sram_data holds the word asked for

    // Macro-ops (the RTU passes them on to the Decode Unit; the macro_if client signals)
    output logic                   req_valid,   // 1 = req_op holds a macro-op
    output logic [101:0]           req_op,      // fmt [101], u [100:53], v [52:5], opcode [4:0]
    input  logic                   req_ready,   // 1 = the Decode Unit takes req_op in this cycle
    input  logic                   resp_valid,  // 1 = resp_result holds the result
    input  logic [3*WLEN-1:0]      resp_result, // z [47:32], y [31:16], x [15:0]; a compare gives 1 or 0 in x
    output logic                   resp_ready,  // 1 = the IU takes resp_result in this cycle

    // Debug
    output state_t                 state_q,
    output state_t                 state_d,
    output sram_state_t            sram_state_q,
    output sram_state_t            sram_state_d,
    output dec_state_t             dec_state_q,
    output dec_state_t             dec_state_d,
    output calc_stage_t            calc_stage_q,
    output calc_stage_t            calc_stage_d,
    output [ADDR_WIDTH-1:0]        dbg_obj_addr,   // w0[15:7] of the reached BV
    output [6:0]                   dbg_obj_cnt     // w0[6:0]  of the reached BV
);

    // Assumption:
    // input ray_origin, ray_dir, bv_count stay same in between start 1-cycle pulse
    // input resp_valid, resp_result stay same until resp_ready and req_valid(?)

    // ------------------------------------------------------------------
    // K shift and the leading-one finder (spec 5d). The finder picks K so that
    // a radius lands in 8..16 before it is squared; the shifter applies K on
    // the way into a request, so it costs no cycles.
    // ------------------------------------------------------------------
    function automatic logic [3:0] leading_one(input logic [14:0] v);
        integer i;
        logic   found;
        begin
            leading_one = 4'd0;
            found       = 1'b0;
            for (i = 14; i >= 0; i--) begin
                if (v[i] && !found) begin
                    leading_one = i[3:0];
                    found       = 1'b1;
                end
            end
        end
    endfunction

    // K = leading_one(raw r) - 10, so r_s is 8 to 16 and r_s^2 is 64 to 256 and
    // never clamps. K > 0 shifts right and rounds, K < 0 shifts left and clamps
    // to 0x7FFF or 0x8000 (spec: "The leading-one finder", "Clamp").
    function automatic logic [15:0] kshift(input logic signed [15:0] v,
                                          input logic signed [4:0]  k);
        logic signed [31:0] w;
        begin
            if (k > 0) begin
                w = {{16{v[15]}}, v} + (32'sd1 <<< (k - 1));
                w = w >>> k;
            end else if (k < 0) begin
                w = {{16{v[15]}}, v} <<< (-k);
            end else begin
                w = {{16{v[15]}}, v};
            end

            if (w > 32'sd32767)       kshift = 16'h7FFF;
            else if (w < -32'sd32768) kshift = 16'h8000;
            else                      kshift = w[15:0];
        end
    endfunction

    // Operand sources for the request fields (spec: "Operand select")
    // Operand sources for the request fields (spec: "Operand select")
    typedef enum logic [3:0] {
        SRC_TC,     // to_centre, then offset (same slots)
        SRC_C,      // centre: BV w2-w4, then the object's w4-w6
        SRC_D,      // ray direction
        SRC_O,      // ray origin
        SRC_ALONG,  // along
        SRC_RS,     // r_s
        SRC_RS2,    // r_s^2
        SRC_OFFSQ,  // |offset_s|^2, kept while the miss compare runs
        SRC_HALF,   // half_s, still at the shifted size
        SRC_T,      // candidate t
        SRC_BESTT,  // best t so far
        SRC_C0156,  // constant 0.0156 (0x0002)
        SRC_PRV,    // the previous macro-op result
        SRC_ZERO    // constant 0
    } src_t;

    // How a request field goes through the size shifter: untouched, by +K
    // (into a squared compare) or by -K (shifting a result back)
    typedef enum logic [1:0] {
        SH_NONE = 2'd0,
        SH_K    = 2'd1,
        SH_NK   = 2'd2
    } shift_t;


    // FSM States
    // Disable for the debug build
    //typedef enum logic [1:0] {
    //    S_IDLE       = 2'd0,
    //    S_RTU_LOAD   = 2'd1,
    //    S_PROCESS_BV = 2'd2,
    //    S_CHECKOUT   = 2'd3
    //} state_t;

    //typedef enum logic [1:0] {
    //    S_SRAM_IDLE = 2'd0,
    //    S_SRAM_SEND = 2'd1,
    //    S_SRAM_WAIT = 2'd2,
    //    S_SRAM_NEXT = 2'd3
    //} sram_state_t;

    //typedef enum logic [1:0] {
    //    S_DEC_IDLE = 2'd0,
    //    S_DEC_SEND = 2'd1,
    //    S_DEC_WAIT = 2'd2,
    //    S_DEC_DONE = 2'd3
    //} dec_state_t;
    
    // WiP not implemented
    // p = ray * t
    // outward_normal = (p - bv_origin) / bv_r
    // front_face = (dot(ray_dir, normal) < 0)
    // normal = front_face ? outward_normal : -outward_normal;
    // hit_flip =
    //typedef enum logic [3:0] {
    //    CALC_A            = 4'd0,
    //    CALC_OC           = 4'd1,
    //    CALC_OC_DOT       = 4'd2,
    //    CALC_H            = 4'd3,
    //    CALC_R2           = 4'd4,
    //    CALC_C            = 4'd5,
    //    CALC_AC           = 4'd6,
    //    CALC_H2           = 4'd7,
    //    CALC_DISCRIMINANT = 4'd8,
    //    CALC_HIT          = 4'd9,
    //    CALC_SQRTD        = 4'd10,
    //    CALC_NUMERATOR    = 4'd11,
    //    CALC_T            = 4'd12
    // WiP for hit_flip

    //} calc_stage_t;

    //state_t state_q, state_d;
    //sram_state_t sram_state_q, sram_state_d;
    //dec_state_t dec_state_q, dec_state_d;
    //calc_stage_t calc_stage_q;

    // Next-State Combinational Logic
    // Main State Machine
    always_comb begin
        state_d = state_q;
        case (state_q)
            S_IDLE: begin
                // Boot system after start signal
                if (start) state_d = S_RTU_LOAD;
            end
            S_RTU_LOAD: begin
                // Routing check for bv_count
                if (bv_count == 0) state_d = S_CHECKOUT;
                else state_d = S_PROCESS_BV;
            end
            S_PROCESS_BV: begin
                // Checkout after computed all bv object intersection
                if (bv_phase == PH_NEXT) begin
                    if (bv_index + 5'd1 >= bv_count) state_d = S_CHECKOUT;
                end
            end
            S_CHECKOUT: begin
                // Return to IDLE state after reporting (done is pulsed for one
                // cycle by the sequential block)
                state_d = S_IDLE;
            end

            default: state_d = S_IDLE;
        endcase
    end

    // SRAM State Machine
    always_comb begin
        sram_state_d = sram_state_q;
        case (sram_state_q)
            S_SRAM_IDLE: begin
                // Load 1st Address and send only if bv_count is valid
                if (sram_start) sram_state_d = S_SRAM_SEND;
            end
            S_SRAM_SEND: begin
                // Move to WAIT state after setting sram_rd
                sram_state_d = S_SRAM_WAIT;
            end
            S_SRAM_WAIT: begin
                // Capture the word; sram_rd is combinational, so the next word
                // is requested in this cycle and a word costs 2 cycles
                if (sram_valid) begin
                    if (sram_w_index == sram_w_last) sram_state_d = S_SRAM_NEXT;
                end
                
                // Scrapped Version
                // Move to next word after latch and hold until all calculation to move to next SRAM BV object (i increment)
                // Radius: w0 -> w1 condition: Latched and Decoder available
                //if (!bv_r_ready)
                //    if (sram_latch && dec_state_q == S_DEC_IDLE) sram_state_d = S_SRAM_NEXT;
                // Origin: w1 -> w2 condition: Latched and Decoder available (Noted: Removed wait for bv_r2 latching as the calculation sequence optimized to local register reduction)
                //else if (calc_stage_q == CALC_OC)
                    // w2 -> w4 condition: Latched 
                //    if (sram_latch && dec_state_q == S_DEC_IDLE) sram_state_d = S_SRAM_NEXT; // Removed (&& bv_r_ready &&) as the calculation sequence optimized to local register reduction
                    // Move to next SRAM BV object (i increment) condition: after all calculation
                //    else if (bv_origin_ready)
                //        if (dec_state_q == S_DEC_DONE) sram_state_d = S_SRAM_NEXT;

            end
            S_SRAM_NEXT: begin
                // Finished this SRAM burst
                sram_state_d = S_SRAM_IDLE;
            end

            default: sram_state_d = S_SRAM_IDLE;
        endcase
    end
    
    // Decoder State Machine
    always_comb begin
        dec_state_d = dec_state_q;

        case (dec_state_q)
            S_DEC_IDLE: begin
            
                // Move to SEND state when operand of corresponding steps ready for req_op construction and Decoder available
                if (calc_active) begin
                    // A Decode that is ready takes the macro-op in this cycle
                    if (req_ready) dec_state_d = S_DEC_WAIT;
                    else           dec_state_d = S_DEC_SEND;
                end
            end
            S_DEC_SEND: begin
                // Move to WAIT state for holding req_op and processing latched response after setting req_valid
                if (req_ready) dec_state_d = S_DEC_WAIT;
            end
            S_DEC_WAIT: begin
                // Response queue: latched response
                if (resp_valid) begin
                    // Last step of this BV
                    if (calc_stage_q == CALC_REACH || calc_stage_q == SP_BEST) dec_state_d = S_DEC_DONE;
                    // Iterate next Decoder request
                    else dec_state_d = S_DEC_IDLE;
                end
            end
            S_DEC_DONE: begin
                // Reset after resetting calc_stage_q
                dec_state_d = S_DEC_IDLE;
            end

            default: dec_state_d = S_DEC_IDLE;
        endcase
    end

    // Next step. The BV walk is straight through; the three compares leave it
    // early. The sphere walk adds the half chord and two t gates.
    always_comb begin
        calc_stage_d = calc_stage_q;
        case (calc_stage_q)
            CALC_R2:     calc_stage_d = CALC_TC;
            CALC_TC:     calc_stage_d = CALC_ALONG;
            CALC_ALONG:  calc_stage_d = CALC_TCSQ;
            CALC_TCSQ:   calc_stage_d = CALC_INSIDE;
            CALC_INSIDE: calc_stage_d = CALC_BEHIND;   // overridden when inside
            CALC_BEHIND: calc_stage_d = CALC_M;        // overridden when behind
            CALC_M:      calc_stage_d = CALC_OFF;
            CALC_OFF:    calc_stage_d = CALC_OFFSQ;
            CALC_OFFSQ:  calc_stage_d = CALC_REACH;
            CALC_REACH:  calc_stage_d = CALC_DONE;
            SP_R2:       calc_stage_d = SP_TC;
            SP_TC:       calc_stage_d = SP_ALONG;
            SP_ALONG:    calc_stage_d = SP_M;
            SP_M:        calc_stage_d = SP_OFF;
            SP_OFF:      calc_stage_d = SP_OFFSQ;
            SP_OFFSQ:    calc_stage_d = SP_MISS;
            SP_MISS:     calc_stage_d = SP_HALF2;      // overridden on a miss
            SP_HALF2:    calc_stage_d = SP_SQRT;
            SP_SQRT:     calc_stage_d = SP_T;
            SP_T:        calc_stage_d = SP_TGATE;
            SP_TGATE:    calc_stage_d = SP_T2;         // overridden when it passes
            SP_T2:       calc_stage_d = SP_TGATE2;
            SP_TGATE2:   calc_stage_d = SP_BEST;       // overridden when it fails
            SP_BEST:     calc_stage_d = CALC_DONE;
            default:     calc_stage_d = CALC_DONE;
        endcase

        if (step_done) begin
            if (calc_stage_q == CALC_INSIDE && resp_result[0]) calc_stage_d = CALC_DONE;
            if (calc_stage_q == CALC_BEHIND && resp_result[0]) calc_stage_d = CALC_DONE;
            if (calc_stage_q == SP_MISS    && !resp_result[0]) calc_stage_d = CALC_DONE;
            if (calc_stage_q == SP_TGATE   && resp_result[0])  calc_stage_d = SP_BEST;
            if (calc_stage_q == SP_TGATE2  && !resp_result[0]) calc_stage_d = CALC_DONE;
        end
    end

    // Step table: one row per step (spec 5c for the BV walk, 5d for the sphere
    // walk). Scalar macro-ops only use u.x and v.x, and a row that does not
    // fill the other fields leaves them at the values below.
    always_comb begin
        opcode = M_DOT;
        fmt    = 1'b0;
        src_u  = SRC_TC;
        src_v  = SRC_D;
        sh_u   = SH_NONE;
        sh_v   = SH_NONE;

        case (calc_stage_q)
            // --- bounding volume test (spec 5c) ---
            // 1. r_s^2 = r_s x r_s
            CALC_R2:     begin opcode = M_MUL;      fmt = 1'b0; src_u = SRC_RS;    src_v = SRC_RS;    end
            // 2. to_centre = C - O
            CALC_TC:     begin opcode = M_VSUB;     fmt = 1'b0; src_u = SRC_C;     src_v = SRC_O;     end
            // 3. along = to_centre . D
            CALC_ALONG:  begin opcode = M_DOT;      fmt = 1'b1; src_u = SRC_TC;    src_v = SRC_D;     end
            // 4. |to_centre_s|^2
            CALC_TCSQ:   begin opcode = M_DOT;      fmt = 1'b0; src_u = SRC_TC;    src_v = SRC_TC;    sh_u = SH_K;  sh_v = SH_K;  end
            // 5. does the ray start inside the BV?
            CALC_INSIDE: begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_RS2;   end
            // 6. is the centre behind the start?
            CALC_BEHIND: begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_ALONG; src_v = SRC_ZERO;  end
            // 7. along x D
            CALC_M:      begin opcode = M_SCAL_VEC; fmt = 1'b1; src_u = SRC_ALONG; src_v = SRC_D;     end
            // 8. offset = along x D - to_centre
            CALC_OFF:    begin opcode = M_VSUB;     fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_TC;    end
            // 9. |offset_s|^2
            CALC_OFFSQ:  begin opcode = M_DOT;      fmt = 1'b0; src_u = SRC_TC;    src_v = SRC_TC;    sh_u = SH_K;  sh_v = SH_K;  end
            // 10. is the ray closer to the centre than the radius?
            CALC_REACH:  begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_RS2;   end

            // --- sphere test (spec 5d) ---
            // 1. r_s^2 = r_s x r_s
            SP_R2:       begin opcode = M_MUL;      fmt = 1'b0; src_u = SRC_RS;    src_v = SRC_RS;    end
            // 2. to_centre = C - O
            SP_TC:       begin opcode = M_VSUB;     fmt = 1'b0; src_u = SRC_C;     src_v = SRC_O;     end
            // 3. along = to_centre . D
            SP_ALONG:    begin opcode = M_DOT;      fmt = 1'b1; src_u = SRC_TC;    src_v = SRC_D;     end
            // 4. along x D
            SP_M:        begin opcode = M_SCAL_VEC; fmt = 1'b1; src_u = SRC_ALONG; src_v = SRC_D;     end
            // 5. offset = along x D - to_centre
            SP_OFF:      begin opcode = M_VSUB;     fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_TC;    end
            // 6. |offset_s|^2
            SP_OFFSQ:    begin opcode = M_DOT;      fmt = 1'b0; src_u = SRC_TC;    src_v = SRC_TC;    sh_u = SH_K;  sh_v = SH_K;  end
            // 7. does the ray pass outside the sphere?
            SP_MISS:     begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_OFFSQ; src_v = SRC_RS2;   end
            // 8. r_s^2 - |offset_s|^2, the squared half chord
            SP_HALF2:    begin opcode = M_SUB;      fmt = 1'b0; src_u = SRC_RS2;   src_v = SRC_OFFSQ; end
            // 9. half_s = sqrt(that)
            SP_SQRT:     begin opcode = M_SQRT;     fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_ZERO;  end
            // 10. entry point: t = along - half (half shifted back by K)
            SP_T:        begin opcode = M_SUB;      fmt = 1'b0; src_u = SRC_ALONG; src_v = SRC_HALF;  sh_v = SH_NK; end
            // 11. is the entry point in front of the start?
            SP_TGATE:    begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_C0156; src_v = SRC_T;     end
            // 12. exit point: t = along + half, the ray started inside
            SP_T2:       begin opcode = M_ADD;      fmt = 1'b0; src_u = SRC_ALONG; src_v = SRC_HALF;  sh_v = SH_NK; end
            // 13. is the exit point in front of the start?
            SP_TGATE2:   begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_C0156; src_v = SRC_T;     end
            // 14. is this hit closer than the best one so far?
            SP_BEST:     begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_T;     src_v = SRC_BESTT; end
            default:     ;
        endcase
    end

    // One selector shared by both operands
    function automatic logic [47:0] src_sel(input src_t s);
        case (s)
            SRC_TC:    src_sel = {slot_f, slot_g, slot_h};  // to_centre, then offset
            SRC_C:     src_sel = {slot_c, slot_d, slot_e};  // z, y, x
            SRC_D:     src_sel = ray_dir;
            SRC_O:     src_sel = ray_origin;
            SRC_ALONG: src_sel = {16'd0, 16'd0, slot_a};
            SRC_RS:    src_sel = {16'd0, 16'd0, slot_b};
            SRC_RS2:   src_sel = {16'd0, 16'd0, slot_i};
            SRC_OFFSQ: src_sel = {16'd0, 16'd0, slot_j};
            SRC_HALF:  src_sel = {16'd0, 16'd0, slot_j};
            SRC_T:     src_sel = {16'd0, 16'd0, slot_k};
            SRC_BESTT: src_sel = {16'd0, 16'd0, best_t_q};
            SRC_C0156: src_sel = {16'd0, 16'd0, 16'h0002};
            SRC_PRV:   src_sel = result_q;
            default:   src_sel = 48'd0;
        endcase
    endfunction

    assign u_raw = src_sel(src_u);
    assign v_raw = src_sel(src_v);

    // The size shifter sits between the scratch registers and the request, so
    // the K shift costs no cycles. SH_NK shifts a result back by -K, which is
    // how half_s becomes a real distance again.
    always_comb begin
        u_vec = u_raw;
        v_vec = v_raw;

        if (sh_u != SH_NONE) begin
            u_vec[47:32] = kshift($signed(u_raw[47:32]), (sh_u == SH_NK) ? -k_q : k_q);
            u_vec[31:16] = kshift($signed(u_raw[31:16]), (sh_u == SH_NK) ? -k_q : k_q);
            u_vec[15:0]  = kshift($signed(u_raw[15:0]),  (sh_u == SH_NK) ? -k_q : k_q);
        end
        if (sh_v != SH_NONE) begin
            v_vec[47:32] = kshift($signed(v_raw[47:32]), (sh_v == SH_NK) ? -k_q : k_q);
            v_vec[31:16] = kshift($signed(v_raw[31:16]), (sh_v == SH_NK) ? -k_q : k_q);
            v_vec[15:0]  = kshift($signed(v_raw[15:0]),  (sh_v == SH_NK) ? -k_q : k_q);
        end
    end

    assign req_field = {fmt, u_vec, v_vec, opcode};

    // Internal tracking
    // SRAM read progress
    logic [4:0]  bv_index;
    logic [8:0]  bv_base;       // record address: 17 + 5 * i
    logic [2:0]  sram_w_index;  // word number inside the burst
    logic [2:0]  sram_w_last;   // last word number of this burst
    logic        sram_read;     // 1-cycle pulse: burst complete
    logic        sram_start;    // start a burst
    logic [15:0] sram_word_q;   // last burst word, held one cycle for the phase block
    // Decoder status
    logic        calc_active;   // a step sequence may run
    logic        step_done;     // 1-cycle: the current step's result landed
    bv_phase_t   bv_phase;      // which part of the search is running
    // Local register storage for intermediates (144 bit)
    logic [15:0] slot_a; // one-time local register for each ray processes
    logic [15:0] slot_b, slot_c, slot_d, slot_e, slot_f, slot_g, slot_h, slot_i; // local register for intermediate refresh irregularly throughout the local sram bv item cycle
    // Sphere test scratch: half_s (still at the shifted size) and the candidate
    // distance t, which both t gates and the best-hit compare read
    logic [15:0] slot_j, slot_k;
    // Consumed by the step right after they are produced, so they ride in one
    // register instead of a named slot each: |to_centre_s|^2, along x D,
    // |offset_s|^2 and r_s^2 - |offset_s|^2 are never live at the same time
    logic [47:0] result_q;
    logic signed [4:0] k_q;     // K of the object under test
    // Object loop
    logic [8:0]  obj_addr_q;    // running object address
    logic [6:0]  obj_cnt_q;     // objects left in this BV
    logic        obj_tri;       // current object is a triangle (test still WiP)
    // Best hit of this segment
    logic [15:0] best_t_q;
    logic [8:0]  best_addr_q;
    logic        best_flip_q;
    logic        hit_any_q;
    logic        cand_flip;     // the candidate t came from the exit point
    // Request construction
    src_t         src_u, src_v;
    shift_t       sh_u, sh_v;
    logic [4:0]   opcode;
    logic         fmt;
    logic [47:0]  u_raw, v_raw, u_vec, v_vec;
    logic [101:0] req_field;
    logic [101:0] req_op_q;

    // Handshakes are combinational, so a partner that is already ready answers
    // in the same cycle and no step pays a bubble
    assign req_valid  = (dec_state_q == S_DEC_SEND) ||
                        ((dec_state_q == S_DEC_IDLE) && calc_active);
    assign req_op     = (dec_state_q == S_DEC_SEND) ? req_op_q : req_field;
    assign resp_ready = step_done;
    assign step_done  = (dec_state_q == S_DEC_WAIT) && resp_valid;
    assign calc_active = (bv_phase == PH_CALC) || (bv_phase == PH_SPHERE);

    // 2 cycles per word: the pulse travels with the capture of the word before
    assign sram_rd = (sram_state_q == S_SRAM_SEND) ||
                     ((sram_state_q == S_SRAM_WAIT) && sram_valid &&
                      (sram_w_index != sram_w_last));

    // one burst per phase; the phase block decides which record it reads
    assign sram_start = (state_q == S_PROCESS_BV) &&
                        (sram_state_q == S_SRAM_IDLE) &&
                        ((bv_phase == PH_READ) || (bv_phase == PH_W0) ||
                         (bv_phase == PH_OBJ)  || (bv_phase == PH_HEAD));

    // K and r_s for the BV under test, taken from the radius word as it lands
    // (spec 5d: K = highest 1 bit of the raw radius - 10, so r_s is 8 to 16)
    logic signed [4:0] k_next;
    logic [15:0]       rs_next;

    assign k_next  = $signed({1'b0, leading_one(sram_data[14:0])}) - 5'sd10;
    assign rs_next = kshift($signed(sram_data), k_next);


    // FSM Sequential Iteration
    // Main State Machine
    // WiP
    // PROCESS_BV Handle all of the decision for determining hit and its hittable address, and its shortest t and flipped
    // It should do the reporting at CHECKOUT state after looping all SRAM BV items
    // handshake with SRAM and Decoder module to retrieve the correct hit_addr and hit_t
    // hit_flip, hit_ground should be computed in CHECKOUT state
    // p = ray_origin + ray_dir * hit_t
    // outward_normal = (p - center) / radius
    // front_face = (dot(ray_dir, normal) < 0)
    // normal = front_face ? outward_normal : -outward_normal;
    // hit_flip =
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q    <= S_IDLE;
            done       <= 1'b0;
            hit        <= 1'b0;
            hit_ground <= 1'b0;
            hit_flip   <= 1'b0;
            hit_addr   <= 9'd0;
            hit_t      <= 16'h7FFF;
        end else if (start) begin
            // A new segment starts with no hit; the object and ground tests
            // set these, the BV search alone cannot
            state_q    <= state_d;
            done       <= 1'b0;
            hit        <= 1'b0;
            hit_ground <= 1'b0;
            hit_flip   <= 1'b0;
            hit_addr   <= 9'd0;
            hit_t      <= 16'h7FFF;
        end else begin
            state_q <= state_d;
            
            case (state_q)
                S_IDLE: begin
                end

                S_RTU_LOAD: begin
                end

                S_PROCESS_BV: begin
                end

                S_CHECKOUT: begin
                    // 1-cycle pulse: the hit outputs are valid. hit_ground stays
                    // 0 until the ground test lands.
                    done       <= 1'b1;
                    hit        <= hit_any_q;
                    hit_ground <= 1'b0;
                    hit_t      <= best_t_q;
                    hit_addr   <= best_addr_q;
                    hit_flip   <= best_flip_q;
                end

                default: ;
            endcase
        end
    end

    // SRAM State Machine
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sram_state_q  <= S_SRAM_IDLE;
            sram_addr     <= 9'd17; // BV Address = 17 + 5 * i + word
            sram_w_index  <= 3'd0;  // BV word: w0-w4
            sram_w_last   <= 3'd0;  // last word of this burst
            sram_read     <= 1'b0;
            sram_word_q   <= 16'd0;
            k_q           <= 5'sd0;
            slot_b        <= 16'd0;
            slot_c        <= 16'd0;
            slot_d        <= 16'd0;
            slot_e        <= 16'd0;

        end else if (start) begin
            sram_state_q  <= S_SRAM_IDLE;
            sram_addr     <= 9'd17; // BV Address = 17 + 5 * i + word
            sram_w_index  <= 3'd0;  // BV word: w0-w4
            sram_w_last   <= 3'd0;
            sram_read     <= 1'b0;
            sram_word_q   <= 16'd0;

        end else begin
            sram_state_q <= sram_state_d;

            // 1-cycle pulse
            sram_read <= 1'b0;

            case (sram_state_q)
                // Start at Address 17
                S_SRAM_IDLE: begin
                    if (sram_start) begin
                        // one burst per phase: BV w1-w4, BV w0, object w0, or the
                        // object's w3-w6 (radius first, then the centre)
                        case (bv_phase)
                            PH_W0: begin
                                sram_addr    <= bv_base;
                                sram_w_index <= 3'd0;
                                sram_w_last  <= 3'd0;
                            end
                            PH_OBJ: begin
                                sram_addr    <= obj_addr_q;
                                sram_w_index <= 3'd0;
                                sram_w_last  <= 3'd0;
                            end
                            PH_HEAD: begin
                                sram_addr    <= obj_addr_q + 9'd3;
                                sram_w_index <= 3'd1;
                                sram_w_last  <= 3'd4;
                            end
                            default: begin
                                sram_addr    <= bv_base + 9'd1;
                                sram_w_index <= 3'd1;
                                sram_w_last  <= 3'd4;
                            end
                        endcase
                    end
                end

                // Read SRAM: sram_rd is high this cycle, so load the next address
                S_SRAM_SEND: begin
                    sram_addr <= sram_addr + 9'd1;
                end

                // Process SRAM data. sram_rd is combinational, so the next word
                // is requested in this same cycle and a word costs 2 cycles.
                S_SRAM_WAIT: begin
                    if (sram_valid) begin
                        // held for the phase block, which latches w0 a cycle later
                        sram_word_q <= sram_data;

                        // BV dimensional property for calculation latch on S_DEC_IDLE
                        case (sram_w_index)
                            3'd0: begin
                                // w0: BV object list or object type, see the phase block
                            end
                            3'd1: begin
                                slot_b     <= rs_next; // radius, already shifted by K
                                k_q        <= k_next;
                            end
                            3'd2: begin
                                slot_c     <= sram_data; // z
                            end
                            3'd3: begin
                                slot_d     <= sram_data; // y
                            end
                            3'd4: begin
                                slot_e     <= sram_data; // x
                            end
                            default: ;
                        endcase

                        if (sram_w_index == sram_w_last) begin
                            sram_read <= 1'b1;
                        end else begin
                            sram_addr <= sram_addr + 9'd1;
                            sram_w_index <= sram_w_index + 3'd1;
                        end
                    end
                end

                S_SRAM_NEXT: begin
                    // Finished this SRAM burst, back to IDLE
                end

                default: ;
            endcase
        end
    end

    // Decoder State Machine
    // Decoder Math
    // hit == (h*h - a*c !< 0)
    // oc = bv_origin - ray_origin
    // a = dot(ray_dir, ray_dir)
    // b = -2.0 * dot(ray_dir, oc)
    // c = dot(oc, oc) - bv_r * bv_r
    // h = dot(ray_dir, oc)
    // t = (h + sqrt(h*h - a*c) ) / a
    // WiP not implemented
    // p = ray * t
    // outward_normal = (p - bv_origin) / bv_r
    // front_face = (dot(ray_dir, normal) < 0)
    // normal = front_face ? outward_normal : -outward_normal;
    // hit_flip =
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dec_state_q  <= S_DEC_IDLE;
            bv_index     <= 5'd0;
            bv_base      <= 9'd17;
            req_op_q     <= 102'd0;
            result_q     <= 48'd0;
            slot_a       <= 16'd0;
            slot_f       <= 16'd0;
            slot_g       <= 16'd0;
            slot_h       <= 16'd0;
            dec_state_q  <= S_DEC_IDLE;
            bv_index     <= 5'd0;
            bv_base      <= 9'd17;
            req_op_q     <= 102'd0;
            result_q     <= 48'd0;
            slot_a       <= 16'd0;
            slot_f       <= 16'd0;
            slot_g       <= 16'd0;
            slot_h       <= 16'd0;
            slot_i       <= 16'd0;
            slot_j       <= 16'd0;
            slot_k       <= 16'd0;
            obj_addr_q   <= 9'd0;
            obj_cnt_q    <= 7'd0;
            obj_tri      <= 1'b0;
            best_t_q     <= 16'h7FFF;
            best_addr_q  <= 9'd0;
            best_flip_q  <= 1'b0;
            hit_any_q    <= 1'b0;
            cand_flip    <= 1'b0;

        end else if (start) begin
            // Reset the BV loop for a new ray
            dec_state_q  <= S_DEC_IDLE;
            bv_index     <= 5'd0;
            bv_base      <= 9'd17;
            result_q     <= 48'd0;
            obj_tri      <= 1'b0;
            best_t_q     <= 16'h7FFF;
            best_addr_q  <= 9'd0;
            best_flip_q  <= 1'b0;
            hit_any_q    <= 1'b0;
            cand_flip    <= 1'b0;

        end else begin
            dec_state_q <= dec_state_d;

            // Every BV starts the step sequence again at CALC_R2
            // The step advances only when its macro-op result lands, and every
            // BV restarts the sequence at CALC_R2
            // Every BV restarts at CALC_R2 and every object at SP_R2; a step
            // advances only when its macro-op result lands
            if (bv_phase == PH_CALC || bv_phase == PH_SPHERE) begin
                if (step_done) calc_stage_q <= calc_stage_d;
            end else if (bv_phase == PH_HEAD) begin
                calc_stage_q <= SP_R2;
            end else begin
                calc_stage_q <= CALC_R2;
            end

            // WiP for hit_flip
            // if (state_q == S_CHECKOUT) begin
            //    calc_stage_q       <= CALC_;
            //end

            case (dec_state_q)
                S_DEC_IDLE: begin
                    // Nothing to latch here: the burst words land in the SRAM
                    // block and the step table reads them the cycle after
                end

                S_DEC_SEND: begin
                    // Hold the macro-op until the Decode Unit takes it
                    req_op_q <= req_field;
                end

                S_DEC_WAIT: begin
                    // Accept Decoder response
                    if (resp_valid) begin
                        // Latch resp_result
                        // Note: not sure how to deal with 2 root, in the document at
                        // https://uw-asic.github.io/TinyTracer/encoding/instruction/
                        // it is said that in Functional Units
                        // DIV, SQRT, COS, MAG map to CORDIC. RS1 is the CORDIC operand and RS2 is (see CORDIC)
                        // However, it also noted that in Micro-Op Semantics
                        // U_SQRT	RD <- SQRT(RS1), POS or DIR (FMT); RS2 not used	CORDIC	23
                        // The two-root question does not arise any more: the entry
                        // point is along - half and the exit point along + half, so
                        // a BV test needs no square root and no divide at all.
                        result_q <= resp_result;

                        // local registers held across the BV test
                        // slot_a: along
                        // slot_b: bv_r  (r_s, radius after the K shift)
                        // slot_c: bv_z
                        // slot_d: bv_y
                        // slot_e: bv_x
                        // slot_f: to_centre_z, reused for offset_z
                        // slot_g: to_centre_y, reused for offset_y
                        // slot_h: to_centre_x, reused for offset_x
                        // slot_i: r_s^2
                        case (calc_stage_q)
                            CALC_R2: begin
                                // Latch result (Scalar)
                                slot_i       <= resp_result [15:0];

                                // Internal tracking
                            end

                            CALC_TC: begin
                                // Latch result (Vector 3)
                                {slot_f, slot_g, slot_h} <= resp_result;

                                // Internal tracking
                            end

                            CALC_ALONG: begin
                                // Latch result (Scalar)
                                slot_a       <= resp_result [15:0];

                                // Internal tracking
                            end

                            CALC_TCSQ: begin
                                // Nothing to keep: the next step reads result_q

                                // Internal tracking
                            end

                            CALC_INSIDE: begin
                                // Latch result (Compare)
                                if (resp_result[0]) begin
                                    // The ray starts inside the BV: objects
                                    // inside can still be hit, so reach
                                end else begin
                                end
                            end

                            CALC_BEHIND: begin
                                // Latch result (Compare)
                                if (resp_result[0]) begin
                                    // Centre behind the start: moving along the
                                    // ray only takes it farther away
                                end else begin
                                end
                            end

                            CALC_M: begin
                                // Nothing to keep: CALC_OFF reads result_q

                                // Internal tracking
                            end

                            CALC_OFF: begin
                                // Latch result (Vector 3)
                                {slot_f, slot_g, slot_h} <= resp_result;

                                // Internal tracking
                            end

                            CALC_OFFSQ: begin
                                // Nothing to keep: CALC_REACH reads result_q

                                // Internal tracking
                            end

                            CALC_REACH: begin
                                // Latch result (Compare): reach reads w0, skip
                                // moves straight to the next BV
                                bv_phase     <= resp_result[0] ? PH_W0 : PH_NEXT;
                            end

                            // sphere test (spec 5d)
                            SP_R2: begin
                                // Latch result (Scalar)
                                slot_i       <= resp_result [15:0];
                            end

                            SP_TC: begin
                                // Latch result (Vector 3)
                                {slot_f, slot_g, slot_h} <= resp_result;
                            end

                            SP_ALONG: begin
                                // Latch result (Scalar)
                                slot_a       <= resp_result [15:0];
                            end

                            SP_M: begin
                                // Nothing to keep: SP_OFF reads result_q
                            end

                            SP_OFF: begin
                                // Latch result (Vector 3): offset replaces to_centre
                                {slot_f, slot_g, slot_h} <= resp_result;
                            end

                            SP_OFFSQ: begin
                                // Latch result (Scalar): the miss compare and the
                                // half chord both read it, so it cannot ride in
                                // result_q across the compare
                                slot_j       <= resp_result [15:0];
                            end

                            SP_MISS: begin
                                // Latch result (Compare): a miss ends this object
                            end

                            SP_HALF2: begin
                                // Nothing to keep: SP_SQRT reads result_q
                            end

                            SP_SQRT: begin
                                // Latch result (Scalar): half_s, still at the shifted size
                                slot_j       <= resp_result [15:0];
                            end

                            SP_T: begin
                                // Latch result (Scalar): entry point
                                slot_k    <= resp_result [15:0];
                                cand_flip <= 1'b0;
                            end

                            SP_T2: begin
                                // Latch result (Scalar): exit point, ray started inside
                                slot_k    <= resp_result [15:0];
                                cand_flip <= 1'b1;
                            end

                            SP_BEST: begin
                                // Latch result (Compare): closer than the best so far
                                if (resp_result[0]) begin
                                    best_t_q    <= slot_k;
                                    best_addr_q <= obj_addr_q;
                                    best_flip_q <= cand_flip;
                                    hit_any_q   <= 1'b1;
                                end
                            end

                            // WiP for hit_flip

                            default: ;
                        endcase
                    end
                end

                S_DEC_DONE: begin
                    // Reset for next BV object
                end

                default: ;
            endcase

            // Per-BV phase: read the record, walk the steps, read w0, then one
            // object at a time, then advance
            case (bv_phase)
                PH_READ: if (sram_read) bv_phase <= PH_CALC;
                // the three compares end the BV: inside -> reach, behind ->
                // skip, and the last one decides reach or skip
                PH_CALC: if (step_done) begin
                             if (calc_stage_q == CALC_INSIDE && resp_result[0])      bv_phase <= PH_W0;
                             else if (calc_stage_q == CALC_BEHIND && resp_result[0]) bv_phase <= PH_NEXT;
                             else if (calc_stage_q == CALC_REACH)                    bv_phase <= resp_result[0] ? PH_W0 : PH_NEXT;
                         end
                // w0 of the BV: where its objects start and how many there are
                PH_W0:   if (sram_read) begin
                             obj_addr_q <= sram_word_q[15:7];
                             obj_cnt_q  <= sram_word_q[6:0];
                             bv_phase   <= (sram_word_q[6:0] != 7'd0) ? PH_OBJ : PH_NEXT;
                         end
                // w0 of one object: bit 0 picks sphere or triangle. The triangle
                // test is still a WiP, so a triangle is stepped over for now.
                PH_OBJ:  if (sram_read) begin
                             obj_tri  <= ~sram_word_q[0];
                             bv_phase <= sram_word_q[0] ? PH_HEAD : PH_OBJ_NEXT;
                         end
                // w3-w6 of the object: radius first, then the centre
                PH_HEAD: if (sram_read) bv_phase <= PH_SPHERE;
                // the sphere sequence ends on a miss, on a failed exit gate, or
                // after the best-hit compare
                PH_SPHERE: if (step_done) begin
                             if (calc_stage_q == SP_MISS && !resp_result[0])        bv_phase <= PH_OBJ_NEXT;
                             else if (calc_stage_q == SP_TGATE2 && !resp_result[0]) bv_phase <= PH_OBJ_NEXT;
                             else if (calc_stage_q == SP_BEST)                      bv_phase <= PH_OBJ_NEXT;
                         end
                // +7 words for a sphere, +12 for a triangle, one object less
                PH_OBJ_NEXT: begin
                    bv_phase   <= (obj_cnt_q > 7'd1) ? PH_OBJ : PH_NEXT;
                    obj_cnt_q  <= obj_cnt_q - 7'd1;
                    obj_addr_q <= obj_addr_q + (obj_tri ? 9'd12 : 9'd7);
                end
                PH_NEXT: begin
                    bv_phase <= PH_READ;
                    if (bv_index + 5'd1 < bv_count) begin
                        bv_index <= bv_index + 5'd1;
                        bv_base  <= bv_base + 9'd5;
                    end
                end
                default: ;
            endcase
        end
    end

    // Debug bundle: the first object address and count of the last reached BV
    assign dbg_obj_addr = obj_addr_q;
    assign dbg_obj_cnt  = obj_cnt_q;

endmodule
