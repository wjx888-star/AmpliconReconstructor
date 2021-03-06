#!/usr/bin/env python2

"""
Jens Luebeck
UC San Diego, Bioinformatics & Systems Biology
jluebeck@ucsd.edu
"""

import os
import sys
import time
import bisect
import argparse
import subprocess
import numpy as np
import matplotlib

matplotlib.use('Agg')
from bionanoUtil import *
import matplotlib.pyplot as plt
from ContigAlignmentGraph import *
from collections import defaultdict

unaligned_label_cutoff = 20
search_upper_cutoff_labels = 500
unaligned_size_lower_cutoff = 200000
unaligned_size_upper_cutoff = 5000000


# identify unaligned regions in contigs
def get_unaligned_segs(aln_path, aln_flist):
    contig_aln_dict = defaultdict(list)
    contig_unaligned_regions = defaultdict(list)
    for f in aln_flist:
        # parse the alnfile
        a_c_id, a_list = parse_seg_alignment_file(aln_path + f)
        aln_obj = SA_Obj(a_c_id, a_list)
        contig_id = aln_obj.contig_id
        contig_aln_dict[contig_id].append(aln_obj)

    # extract aligned regions
    for c_id, a_struct_list in contig_aln_dict.items():
        contig_free_lab_set = set(range(len(contig_cmaps[c_id])))
        for a_struct in a_struct_list:
            curr_c_range_tup = a_struct.contig_endpoints
            curr_lab_range_set = set(range(curr_c_range_tup[0], curr_c_range_tup[1] + 1))
            contig_free_lab_set -= curr_lab_range_set

        # extract unaligned regions using aligned region labels

        # determine what percent is aligned, skip if too much unaligned in contig.
        percent_unaligned = float(len(contig_free_lab_set)) / len(contig_cmaps[c_id])
        if percent_unaligned > 0.9:
            continue

        sorted_contig_free_labs = sorted(list(contig_free_lab_set))
        chunk_list = []
        prev = -2
        for i in sorted_contig_free_labs:
            if i - prev > 1:
                chunk_list.append([])

            chunk_list[-1].append(i)
            prev = i

        # check if unaligned region is large
        for l in chunk_list:
            unaligned_size = contig_cmaps[c_id][l[-1] + 1] - contig_cmaps[c_id][l[0] + 1]
            # check if too small
            if l[-1] - l[0] > unaligned_label_cutoff and unaligned_size > unaligned_size_lower_cutoff:
                # check if too big:
                if unaligned_size > unaligned_size_upper_cutoff:
                    contig_unaligned_regions[c_id].append(l[:search_upper_cutoff_labels])

                else:
                    # add the unaligned region
                    contig_unaligned_regions[c_id].append(l)

    return contig_unaligned_regions


# write the unaligned regions, do some bookkeeping, mapping contig_id to some set of labels.
# return a mapping of the new contig_id and labels involved
def write_unaligned_cmaps(contig_unaligned_regions, output_prefix, enzyme):
    max_contig_id = max([int(x) for x in contig_cmaps.keys()])
    unaligned_region_contig_dict = {}
    unaligned_contig_id_dict = {}
    nmaps = sum([len(x) for x in contig_unaligned_regions.values()])
    cmap_header = "# CMAP File Version: 0.1\n# Label Channels:  1\n# Nickase Recognition Site 1:    " + enzyme + "\n# Enzyme1:  " + enzyme + "\n# Number of Consensus Nanomaps: " + str(
        nmaps) + "\n#h CMapId ContigLength    NumSites    SiteID  LabelChannel    Position    StdDev  Coverage    Occurrence\n#f int  float   int int int float   float   int int\n"
    unaligned_region_filename = output_prefix + "contig_unaligned_regions.cmap"
    with open(unaligned_region_filename, 'w') as outfile:
        outfile.write(cmap_header)
        total_unaligned_segs = 0
        for c_id, all_regions in contig_unaligned_regions.items():
            for l in all_regions:
                total_unaligned_segs += 1
                try:
                    map_end_pos = contig_cmaps[c_id][l[-1] + 2]
                except KeyError:
                    map_end_pos = contig_lens[c_id]

                pos_l = [contig_cmaps[c_id][x + 1] for x in l]
                curr_id = str(max_contig_id + total_unaligned_segs)
                unaligned_region_contig_dict[curr_id] = {str(ind + 1): str(x + 1) for ind, x in enumerate(l)}
                unaligned_contig_id_dict[curr_id] = c_id

                p0 = pos_l[0]
                map_len_str = str(map_end_pos - p0)
                for ind, i in enumerate(pos_l):
                    out_list = [curr_id, map_len_str, str(len(l)), str(ind + 1), "1", str(i - p0), "1.0", "1", "1"]
                    outfile.write("\t".join(out_list) + "\n")

                out_list = [curr_id, map_len_str, str(len(l)), str(ind + 1), "0", map_len_str, "1.0", "1", "1"]
                outfile.write("\t".join(out_list) + "\n")

    return unaligned_region_contig_dict, unaligned_region_filename, unaligned_contig_id_dict


# deprecated and unused function
def detections_to_graph(outfile, bpg_list):
    for i in bpg_list:
        seg_size = int(i[2]) - int(i[1])
        outfile.write("sequence\t")
        outfile.write(i[0] + ":" + i[1] + "-\t")
        outfile.write(i[0] + ":" + i[2] + "+\t")
        outfile.write("2.0\t0\t" + str(seg_size) + "\t0\n")


# deprecated and unused function
def detections_to_key(outfile, keyfile_info):
    for i in keyfile_info:
        outfile.write(i[0] + "\t" + i[1] + ":" + i[2] + "-|" + i[1] + ":" + i[3] + "+\t0\n")


# write the aligned contig labels to a file
def write_aligned_labels(a_dir, aln_flist, w_dir):
    contig_to_aligned_label_list = defaultdict(set)
    for f in aln_flist:
        a_c_id, a_list = parse_seg_alignment_file(a_dir + f)
        aln_obj = SA_Obj(a_c_id, a_list)
        contig_id = aln_obj.contig_id
        contig_ends = aln_obj.contig_endpoints
        contig_label_set = set(range(min(contig_ends), max(contig_ends) + 1))
        contig_to_aligned_label_list[contig_id] |= contig_label_set

    outfile_name = w_dir + "contig_aligned_labels_nontip.txt"
    with open(outfile_name, 'w') as outfile:
        outfile.write("#contig_id [space delimited list of labels]\n")
        for i in contig_to_aligned_label_list:
            lab_list = [str(x - 1) for x in sorted(list(contig_to_aligned_label_list[i]))]
            line = " ".join([i] + lab_list)
            outfile.write(line + "\n")

    return outfile_name


# write a new AA graph file and a new CMAP reflecting the added segments
def rewrite_graph_and_CMAP(segs_fname, graphfile, bpg_list, enzyme, outdir):
    # read graph
    graphfile_lines = []
    with open(graphfile) as infile:
        for line in infile:
            graphfile_lines.append(line)

    gbase = os.path.splitext(os.path.basename(graphfile))[0]
    new_graphfile = outdir + gbase + "_includes_detected.txt"
    with open(new_graphfile, 'w') as outfile:
        for line in graphfile_lines:
            if line.startswith("BreakpointEdge:"):
                detections_to_graph(outfile, bpg_list)

            outfile.write(line)

    print("Creating new CMAP")
    # seg_outname = os.path.splitext(segs_fname)[0] + "_includes_detected"
    sbase = os.path.splitext(os.path.basename(segs_fname))[0]
    seg_outname = outdir + sbase + "_includes_detected"
    fa_name = ""
    if REF == "GRCh38" or REF == "hg38":
        fa_name = "hg38full.fa"
    elif REF == "hg19":
        fa_name = "hg19full.fa"

    cmd = "python2 {}/generate_cmap.py -g {} -r {}/{}/{} -e {} -o {}".format(
        os.environ['AR_SRC'], new_graphfile, os.environ['AA_DATA_REPO'], REF, fa_name, enzyme, seg_outname)

    subprocess.call(cmd, shell=True)


def detections_to_seg_alignments(w_dir, aln_files, ref_file, unaligned_cid_d, unaligned_label_trans, id_start, prefix):
    # must indicate that the reference genome used (field in the head)
    ref_genome_cmaps = parse_cmap(ref_file)
    ref_genome_key_file = os.path.splitext(ref_file)[0] + "_key.txt"
    ref_genome_key_dict = parse_keyfile(ref_genome_key_file)

    seg_dir_count = defaultdict(int)
    bpg_list = []
    aln_num = 0
    u_id_lookup = {}
    print("aln_files len", len(aln_files))
    for f in aln_files:
        f_fields = os.path.splitext(f)
        f_fields = os.path.splitext(f)
        # outname = w_dir + f_fields[0] + "_corrected" + f_fields[1]
        head_list = []
        aln_field_list = []
        with open(w_dir + f) as infile:
            for i in range(3):
                head_list.append(next(infile))

            for line in infile:
                aln_field_list.append(line.rstrip().rsplit("\t"))

        # get direction
        meta_list = []
        contig_id = head_list[1].rsplit("\t")[0][1:-1]
        contig_dir = head_list[1].rsplit("\t")[0][-1]
        try:
            trans_contig_id = unaligned_cid_d[contig_id]
        except KeyError:
            continue

        # set up the breakpoint graph stuff
        ref_genome_id = aln_field_list[0][0]
        chromID = ref_genome_key_dict[ref_genome_id][0]
        p1 = int(ref_genome_cmaps[ref_genome_id][int(aln_field_list[0][2])])
        p2 = int(ref_genome_cmaps[ref_genome_id][int(aln_field_list[-1][2])])
        if p1 > p2:
            temp = p2
            p2 = p1
            p1 = temp

        if (chromID, str(p1 - 10), str(p2 + 10)) not in bpg_list:  # use 10bp padding on aligned segment
            bpg_list.append((chromID, str(p1 - 10), str(p2 + 10)))
            aln_num += 1
            unique_id = str(id_start + aln_num)
            u_id_lookup[(chromID, str(p1 - 10), str(p2 + 10))] = unique_id

        else:
            unique_id = u_id_lookup[(chromID, str(p1 - 10), str(p2 + 10))]

        meta_list.append(unique_id)
        if contig_dir == "-":
            aln_field_list = aln_field_list[::-1]

        meta_list[0] += contig_dir
        meta_list.append(head_list[1].rsplit("\t")[1])
        meta_list.append("False")
        meta_string = "#" + "\t".join(meta_list) + "\n"

        # reverse the reference sequence if "-"
        isRev = "_r" if contig_dir == "-" else ""

        outname = prefix + "_" + trans_contig_id + "_" + unique_id + "_rg" + isRev + "_aln.txt"
        with open(w_dir + outname, 'w') as outfile:
            outfile.write(head_list[0])
            outfile.write(meta_string)
            outfile.write(head_list[2])
            curr_score = 0.0
            lchange = 0
            first = min(int(aln_field_list[0][2]), int(aln_field_list[-1][2]))
            for l in aln_field_list:
                trans_lab = unaligned_label_trans[contig_id][l[3]]
                new_l = [trans_contig_id, unique_id, trans_lab, str(int(l[2]) - first + 1)] + l[4:7] + [str(curr_score),
                                                                                                        str(lchange)]
                curr_score += float(l[-1])
                lchange = l[-1]
                outfile.write("\t".join(new_l) + "\n")

        seg_dir_count[(trans_contig_id, contig_dir)] += 1

    return bpg_list


def run_SegAligner(contig_file, ref_file, arg_list, a_dir):
    # argstring = " ".join(arg_list)
    cmd_vect = [os.environ['SA_SRC'] + "/SegAligner", ref_file, contig_file] + arg_list
    with open(a_dir + "SA_run.out", 'w') as saout:
        subprocess.call(cmd_vect, stdout=saout)


def make_score_plots(scores_file, fpath):
    scoring_dict = defaultdict(list)
    with open(scores_file) as infile:
        head = next(infile)
        for line in infile:
            fields = line.rstrip().rsplit("\t")
            scoring_dict[int(fields[0])].append(float(fields[2]))

    num_blue = int(round(0.15 * min(500, len(contig_cmaps))))
    for i in scoring_dict:
        fig = plt.figure()
        left_ind = len(scoring_dict[i]) / 2 + 1
        x_vals = sorted(scoring_dict[i], reverse=True)
        y_vals = np.log(range(1, len(x_vals) + 1))
        cols = ["grey"] * 25 + ["b"] * num_blue + ["grey"] * (len(x_vals) - (25 + num_blue))
        plt.scatter(x_vals, y_vals, c=cols, edgecolors='none')
        plt.ylabel("ln(E)", fontsize=14)
        plt.xlabel("S", fontsize=14)
        plt.title(str(i), fontsize=14)
        fig.savefig(fpath + "s_dist_" + str(i) + ".png", dpi=300)
        plt.close()


# main
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Wrap scaffolding process for breakpoint graph and OM data or long reads, includes wrapping SegAligner OM alignment.")
    parser.add_argument("-s", "--segs",
                        help="reference genome cmap file. Key file must be present in same directory and be named [CMAP]_key.txt",
                        required=True)
    parser.add_argument("-c", "--contigs", help="contigs cmap file", required=True)
    parser.add_argument("-g", help="AA-formatted breakpoint graph file", required=True)
    parser.add_argument("-o", "--output_prefix", type=str, default="SA_segs", help="output alignment filename prefix")
    parser.add_argument("-d", "--output_directory",
                        help="Path to directory where new files are created. Default is CWD.")
    parser.add_argument("-t", "--threads", help="number of threads to use (default 8), recommend 16+", type=int,
                        default=8)
    parser.add_argument("-r", "--ref", help="Reference genome build. Must be same as AA graph",
                        choices=["hg19", "GRCh38"], required=True)
    parser.add_argument("-e", "--enzyme", help="labeling enzyme", choices=["BspQI", "DLE1"], required=True)
    parser.add_argument("--plot_scores", help="Save plots of the distributions of segment scores", action='store_true',
                        default=False)
    parser.add_argument("--no_tip_aln", help="Disable tip alignment step", action='store_true')
    parser.add_argument("--min_map_len",
                        help="minimum number of labels on map contig when aligning (default 10). Slightly larger values (~12) better for Saphyr data.",
                        type=int, default=10)
    parser.add_argument("--no_ref_search", help="Do not search unaligned regions against reference genome",
                        action='store_true')
    parser.add_argument("-i", "--instrument", choices=["Irys", "Saphyr"], required=True)
    parser.add_argument("--xmap",
                        help="Supply your own alignments (do not use SegAligner for initial alignments. Must be xmap formatted. Xmap alignments will be converted and re-written SegAligner format.")
    parser.add_argument("--swap_xmap_RQ",
                        help="When AS converts to its alignment format, set this argument if reference segments are aligned to contigs/reads (i.e. reference and query have been swapped)",
                        action='store_true', default=False)

    args = parser.parse_args()
    if args.swap_xmap_RQ and not args.xmap:
        parser.error("--swap_xmap_RQ requires --xmap [your_xmap_file.xmap]. Are you supplying your own alignments?")

    print("results will be stored in " + args.output_directory)

    if not args.output_directory.endswith("/"): args.output_directory += "/"

    a_dir = args.output_directory + "alignments/"
    if not os.path.exists(a_dir): os.makedirs(a_dir)

    min_map_len = args.min_map_len  # the default
    nthreads = args.threads
    gen = "1" if args.instrument == "Irys" else "2"

    contig_cmaps = parse_cmap(args.contigs)
    seg_cmaps = parse_cmap(args.segs)
    contig_lens = get_cmap_lens(args.contigs)
    REF = args.ref
    ref_genome_file = os.environ['AR_SRC'] + "/ref_genomes/" + REF + "_" + args.enzyme + ".cmap"

    # Do alignment with SegAligner if not using own XMAP
    if not args.xmap:
        print("Doing segment alignments with SegAligner")
        arg_list = ["-nthreads=" + str(nthreads), "-min_labs=" + str(min_map_len),
                    "-prefix=" + a_dir + args.output_prefix, "-gen=" + gen]
        # #CONTIG SEG ALIGNMENTS
        # print arg_list
        run_SegAligner(args.contigs, args.segs, arg_list, a_dir)

        # get the scoring thresholds.
        if args.plot_scores:
            print("Plotting score distributions")
            make_score_plots(a_dir + args.output_prefix + "_all_scores.txt", args.output_directory)

    # if xmap supplied, read it and re-write the alignments into the alignments/ directory
    else:
        refLenD = get_cmap_lens(args.segs)
        qryLenD = get_cmap_lens(args.contigs)
        xmapD = parse_generic_xmap(args.xmap, qryLenD, refLenD, args.swap_xmap_RQ)
        xmap_to_SA_aln(xmapD, a_dir, "XMAP_segs", seg_cmaps, contig_cmaps)

    # SCORING OF UNALIGNED REGIONS - this will always use SegAligner.
    # Use no_ref_search if you do not wish to detect additional segments on the set of contigs
    # with alignments to your breakpoint graph segments.
    if args.no_ref_search:
        print("REF SEARCH OFF, SKIPPING REF SEARCH STEP")

    else:
        print("Doing unaligned region detection")
        # extract aligned regions
        aln_flist = [x for x in os.listdir(a_dir) if
                     "_aln.txt" in x and "flipped" not in x and "_ref_" not in x and "rg" not in x]
        # extract the unaligned regions given the alignments
        contig_unaligned_regions = get_unaligned_segs(a_dir, aln_flist)
        if not contig_unaligned_regions:
            print(
                "No extra-large unaligned regions found after aligning segments to contigs. Skipping reference genome search.")

        else:
            unaligned_label_trans, unaligned_region_filename, unaligned_cid_d = write_unaligned_cmaps(
                contig_unaligned_regions, args.output_directory, args.enzyme)
            unaligned_fname_prefix = args.output_prefix + "_ref_search"
            arg_list = ["-nthreads=" + str(nthreads), "-min_labs=" + str(min_map_len),
                        "-prefix=" + a_dir + unaligned_fname_prefix, "-detection", "-gen=" + gen]
            # CONTIG UNALIGNED REGION ALIGNMENTS
            run_SegAligner(ref_genome_file, unaligned_region_filename, arg_list, a_dir)
            with open(args.g) as infile:
                index_start = sum(1 for _ in infile if _.startswith("sequence"))

            aln_flist = [x for x in os.listdir(a_dir) if "_aln.txt" in x and unaligned_fname_prefix in x]
            if aln_flist:
                print("Found new segments, re-writing graph and CMAP")
                bpg_list = detections_to_seg_alignments(a_dir, aln_flist, ref_genome_file, unaligned_cid_d,
                                                        unaligned_label_trans, index_start, args.output_prefix)
                rewrite_graph_and_CMAP(args.segs, args.g, bpg_list, args.enzyme, args.output_directory)
                # remove "SA_ref_" files (temporary alignments)
                # subprocess.call("rm " + a_dir + "SA_ref_*_aln.txt 2>/dev/null", shell=True)

            subprocess.call("rm " + args.output_directory + "contig_unaligned_regions.cmap", shell=True)

    print("Completed " + time.ctime(time.time()) + "\n")
