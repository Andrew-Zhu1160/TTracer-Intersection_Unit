`default_nettype none
//the unit test around this specific module, not top module
//the external device this module talk to will be mocked
//according to their intended behavior
`include "../src/rtu/intersection_unit.sv"
`timescale 1ns / 1ps

/* Unit testbench for intersection_unit. Cocotb drives these wires from test.py.
*/
module tb_intersection_unit ();

  // Dump the signals to a VCD file. You can view it with gtkwave or surfer.
  initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb_intersection_unit);
    #1;
  end

  reg         clk;
  reg         rst_n;
  reg         start;
  wire        done;
  wire        hit;
  wire        hit_ground;
  wire [15:0] hit_t;
  wire [8:0]  hit_addr;
  wire        hit_flip;

  reg [47:0]  ray_origin;
  reg [47:0]  ray_dir;
  reg [4:0]   bv_count;

  wire [8:0]  sram_addr;
  wire        sram_rd;
  reg [15:0]  sram_data;
  reg         sram_valid;

  wire        req_valid;
  wire [101:0] req_op;
  reg         req_ready;
  reg         resp_valid;
  reg [47:0]  resp_result;
  wire        resp_ready;

  intersection_unit iu (
      .clk        (clk),
      .rst_n      (rst_n),
      .start      (start),
      .done       (done),
      .hit        (hit),
      .hit_ground (hit_ground),
      .hit_t      (hit_t),
      .hit_addr   (hit_addr),
      .hit_flip   (hit_flip),
      .ray_origin (ray_origin),
      .ray_dir    (ray_dir),
      .bv_count   (bv_count),
      .sram_addr  (sram_addr),
      .sram_rd    (sram_rd),
      .sram_data  (sram_data),
      .sram_valid (sram_valid),
      .req_valid  (req_valid),
      .req_op     (req_op),
      .req_ready  (req_ready),
      .resp_valid (resp_valid),
      .resp_result(resp_result),
      .resp_ready (resp_ready)
  );

endmodule
