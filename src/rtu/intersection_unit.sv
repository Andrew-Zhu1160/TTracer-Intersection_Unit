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
    typedef enum logic [3:0] {
        CALC_R2     = 4'd0,   // r_s^2 = r_s x r_s                 M_MUL fmt 0       3
        CALC_TC     = 4'd1,   // to_centre = C - O                 M_VSUB            7
        CALC_ALONG  = 4'd2,   // along = to_centre . D             M_DOT fmt 1      11
        CALC_TCSQ   = 4'd3,   // |to_centre_s|^2                   M_DOT fmt 0      11  (u,v by K)
        CALC_INSIDE = 4'd4,   // |to_centre_s|^2 < r_s^2 ?         M_LT              3  yes: reach
        CALC_BEHIND = 4'd5,   // along < 0 ?                       M_LT              3  yes: skip
        CALC_M      = 4'd6,   // along x D                         M_SCAL_VEC fmt 1  7
        CALC_OFF    = 4'd7,   // offset = along x D - to_centre    M_VSUB            7
        CALC_OFFSQ  = 4'd8,   // |offset_s|^2                      M_DOT fmt 0      11  (u,v by K)
        CALC_REACH  = 4'd9,   // |offset_s|^2 < r_s^2 ?            M_LT              3  yes: reach
        CALC_DONE   = 4'd10   // this BV is finished
        // WiP for hit_flip

    } calc_stage_t;

    // Per-BV phase: PH_READ reads w1-w4, PH_CALC walks calc_stage_q, PH_W0
    // reads w0 (reach only), PH_NEXT advances to the next BV
    typedef enum logic [1:0] {
        PH_READ = 2'd0,
        PH_CALC = 2'd1,
        PH_W0   = 2'd2,
        PH_NEXT = 2'd3
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
    typedef enum logic [3:0] {
        SRC_TC,     // to_centre, then offset (same slots)
        SRC_C,      // BV centre, straight from the burst words
        SRC_D,      // ray direction
        SRC_O,      // ray origin
        SRC_ALONG,  // along
        SRC_RS,     // r_s
        SRC_RS2,    // r_s^2
        SRC_PRV,    // the previous macro-op result
        SRC_ZERO    // constant 0
    } src_t;


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
                    if (calc_stage_q == CALC_REACH) dec_state_d = S_DEC_DONE;
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

    // Next step of the BV test. The walk is straight through; the three
    // compares leave the sequence early and end the BV.
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
            default:     calc_stage_d = CALC_DONE;
        endcase

        if (step_done) begin
            if (calc_stage_q == CALC_INSIDE && resp_result[0]) calc_stage_d = CALC_DONE;
            if (calc_stage_q == CALC_BEHIND && resp_result[0]) calc_stage_d = CALC_DONE;
        end
    end

    // Step table: one row per step of the BV test (spec 5c). Scalar macro-ops
    // only use u.x and v.x, and a row that does not fill the other fields
    // leaves them at the values below.
    always_comb begin
        opcode = M_DOT;
        fmt    = 1'b0;
        src_u  = SRC_TC;
        src_v  = SRC_D;
        sh_u   = 1'b0;
        sh_v   = 1'b0;

        case (calc_stage_q)
            // 1. r_s^2 = r_s x r_s
            CALC_R2:     begin opcode = M_MUL;      fmt = 1'b0; src_u = SRC_RS;    src_v = SRC_RS;    end
            // 2. to_centre = C - O
            CALC_TC:     begin opcode = M_VSUB;     fmt = 1'b0; src_u = SRC_C;     src_v = SRC_O;     end
            // 3. along = to_centre . D
            CALC_ALONG:  begin opcode = M_DOT;      fmt = 1'b1; src_u = SRC_TC;    src_v = SRC_D;     end
            // 4. |to_centre_s|^2
            CALC_TCSQ:   begin opcode = M_DOT;      fmt = 1'b0; src_u = SRC_TC;    src_v = SRC_TC;    sh_u = 1'b1; sh_v = 1'b1; end
            // 5. does the ray start inside the BV?
            CALC_INSIDE: begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_RS2;   end
            // 6. is the centre behind the start?
            CALC_BEHIND: begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_ALONG; src_v = SRC_ZERO;  end
            // 7. along x D
            CALC_M:      begin opcode = M_SCAL_VEC; fmt = 1'b1; src_u = SRC_ALONG; src_v = SRC_D;     end
            // 8. offset = along x D - to_centre
            CALC_OFF:    begin opcode = M_VSUB;     fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_TC;    end
            // 9. |offset_s|^2
            CALC_OFFSQ:  begin opcode = M_DOT;      fmt = 1'b0; src_u = SRC_TC;    src_v = SRC_TC;    sh_u = 1'b1; sh_v = 1'b1; end
            // 10. is the ray closer to the centre than the radius?
            CALC_REACH:  begin opcode = M_LT;       fmt = 1'b0; src_u = SRC_PRV;   src_v = SRC_RS2;   end
            default:     ;
        endcase
    end

    // One selector shared by both operands
    function automatic logic [47:0] src_sel(input src_t s);
        case (s)
            SRC_TC:    src_sel = {slot_f, slot_g, slot_h};  // to_centre, then offset
            SRC_C:     src_sel = {slot_c, slot_d, slot_e};  // w2, w3, w4 = z, y, x
            SRC_D:     src_sel = ray_dir;
            SRC_O:     src_sel = ray_origin;
            SRC_ALONG: src_sel = {16'd0, 16'd0, slot_a};
            SRC_RS:    src_sel = {16'd0, 16'd0, slot_b};
            SRC_RS2:   src_sel = {16'd0, 16'd0, slot_i};
            SRC_PRV:   src_sel = result_q;
            default:   src_sel = 48'd0;
        endcase
    endfunction

    assign u_raw = src_sel(src_u);
    assign v_raw = src_sel(src_v);

    // The size shifter sits between the scratch registers and the request, so
    // the K shift costs no cycles
    always_comb begin
        u_vec = u_raw;
        v_vec = v_raw;

        if (sh_u) begin
            u_vec[47:32] = kshift($signed(u_raw[47:32]), k_q);
            u_vec[31:16] = kshift($signed(u_raw[31:16]), k_q);
            u_vec[15:0]  = kshift($signed(u_raw[15:0]),  k_q);
        end
        if (sh_v) begin
            v_vec[47:32] = kshift($signed(v_raw[47:32]), k_q);
            v_vec[31:16] = kshift($signed(v_raw[31:16]), k_q);
            v_vec[15:0]  = kshift($signed(v_raw[15:0]),  k_q);
        end
    end

    assign req_field = {fmt, u_vec, v_vec, opcode};

    // Internal tracking
    // SRAM read progress
    logic [4:0]  bv_index;
    logic [8:0]  bv_base;       // record address: 17 + 5 * i
    logic [2:0]  sram_w_index;  // BV Address: w0-w4
    logic [2:0]  sram_w_last;   // last word number of this burst
    logic        sram_read;     // 1-cycle pulse: burst complete
    logic        sram_start;    // start a burst
    // Decoder status
    logic        calc_active;   // the step sequence may run
    logic        step_done;     // 1-cycle: the current step's result landed
    bv_phase_t   bv_phase;      // which part of the BV search is running
    // Local register storage for intermediates (144 bit)
    logic [15:0] slot_a; // one-time local register for each ray processes
    logic [15:0] slot_b, slot_c, slot_d, slot_e, slot_f, slot_g, slot_h, slot_i; // local register for intermediate refresh irregularly throughout the local sram bv item cycle
    // Consumed by the step right after they are produced, so they ride in one
    // register instead of a named slot each: |to_centre_s|^2, along x D and
    // |offset_s|^2 are never live at the same time
    logic [47:0] result_q;
    logic signed [4:0] k_q;     // K of the BV under test
    // BV verdict, exported on the debug bundle
    logic [8:0]  obj_addr_q;    // w0[15:7], first object address
    logic [6:0]  obj_cnt_q;     // w0[6:0], object count
    // Request construction
    src_t         src_u, src_v;
    logic         sh_u, sh_v;
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
    assign calc_active = (bv_phase == PH_CALC);

    // 2 cycles per word: the pulse travels with the capture of the word before
    assign sram_rd = (sram_state_q == S_SRAM_SEND) ||
                     ((sram_state_q == S_SRAM_WAIT) && sram_valid &&
                      (sram_w_index != sram_w_last));

    assign sram_start = (state_q == S_PROCESS_BV) &&
                        (sram_state_q == S_SRAM_IDLE) &&
                        ((bv_phase == PH_READ) || (bv_phase == PH_W0));

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
                    // 1-cycle pulse: the hit outputs are valid
                    done <= 1'b1;
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
            obj_addr_q    <= 9'd0;
            obj_cnt_q     <= 7'd0;
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
            obj_addr_q    <= 9'd0;
            obj_cnt_q     <= 7'd0;

        end else begin
            sram_state_q <= sram_state_d;

            // 1-cycle pulse
            sram_read <= 1'b0;

            case (sram_state_q)
                // Start at Address 17
                S_SRAM_IDLE: begin
                    if (sram_start) begin
                        // w0 alone when the BV was reached, w1-w4 otherwise
                        sram_addr    <= (bv_phase == PH_W0) ? bv_base : bv_base + 9'd1;
                        sram_w_index <= (bv_phase == PH_W0) ? 3'd0 : 3'd1;
                        sram_w_last  <= (bv_phase == PH_W0) ? 3'd0 : 3'd4;
                        obj_addr_q   <= 9'd0;
                        obj_cnt_q    <= 7'd0;
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
                        // BV dimensional property for calculation latch on S_DEC_IDLE
                        case (sram_w_index)
                            3'd0: begin
                                obj_addr_q <= sram_data[15:7];
                                obj_cnt_q  <= sram_data[6:0];
                            end
                            3'd1: begin
                                slot_b     <= rs_next; // bv_r, already shifted by K
                                k_q        <= k_next;
                            end
                            3'd2: begin
                                slot_c     <= sram_data; // bv_z
                            end
                            3'd3: begin
                                slot_d     <= sram_data; // bv_y
                            end
                            3'd4: begin
                                slot_e     <= sram_data; // bv_x
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
            slot_i       <= 16'd0;

        end else if (start) begin
            // Reset the BV loop for a new ray
            dec_state_q  <= S_DEC_IDLE;
            bv_index     <= 5'd0;
            bv_base      <= 9'd17;
            result_q     <= 48'd0;

        end else begin
            dec_state_q <= dec_state_d;

            // Every BV starts the step sequence again at CALC_R2
            // The step advances only when its macro-op result lands, and every
            // BV restarts the sequence at CALC_R2
            if (bv_phase != PH_CALC) calc_stage_q <= CALC_R2;
            else if (step_done)      calc_stage_q <= calc_stage_d;

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

            // Per-BV phase: read the record, walk the steps, read w0, advance
            case (bv_phase)
                PH_READ: if (sram_read) bv_phase <= PH_CALC;
                // the three compares end the BV: inside -> reach, behind ->
                // skip, and the last one decides reach or skip
                PH_CALC: if (step_done) begin
                             if (calc_stage_q == CALC_INSIDE && resp_result[0])      bv_phase <= PH_W0;
                             else if (calc_stage_q == CALC_BEHIND && resp_result[0]) bv_phase <= PH_NEXT;
                             else if (calc_stage_q == CALC_REACH)                    bv_phase <= resp_result[0] ? PH_W0 : PH_NEXT;
                         end
                PH_W0:   if (sram_read) bv_phase <= PH_NEXT;
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
