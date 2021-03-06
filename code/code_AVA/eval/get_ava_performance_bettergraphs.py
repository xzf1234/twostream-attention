r"""Compute action detection performance for the AVA dataset.

Please send any questions about this code to the Google Group ava-dataset-users:
https://groups.google.com/forum/#!forum/ava-dataset-users

Example usage:
python -O get_ava_performance.py \
  -l ava/ava_action_list_v2.1_for_activitynet_2018.pbtxt.txt \
  -g ava_val_v2.1.csv \
  -e ava_val_excluded_timestamps_v2.1.csv \
  -d your_results.csv
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
from collections import defaultdict
import csv
import logging
import pprint
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from ava import object_detection_evaluation
from ava import standard_fields


def print_time(message, start):
    logging.info("==> %g seconds to %s", time.time() - start, message)


def make_image_key(video_id, timestamp):
    """Returns a unique identifier for a video id & timestamp."""
    return "%s,%04d" % (video_id, int(timestamp))


def read_csv(csv_file, class_whitelist=None):
    """Loads boxes and class labels from a CSV file in the AVA format.

    CSV file format described at https://research.google.com/ava/download.html.

    Args:
      csv_file: A file object.
      class_whitelist: If provided, boxes corresponding to (integer) class labels
        not in this set are skipped.

    Returns:
      boxes: A dictionary mapping each unique image key (string) to a list of
        boxes, given as coordinates [y1, x1, y2, x2].
      labels: A dictionary mapping each unique image key (string) to a list of
        integer class lables, matching the corresponding box in `boxes`.
      scores: A dictionary mapping each unique image key (string) to a list of
        score values lables, matching the corresponding label in `labels`. If
        scores are not provided in the csv, then they will default to 1.0.
    """
    start = time.time()
    boxes = defaultdict(list)
    labels = defaultdict(list)
    scores = defaultdict(list)
    reader = csv.reader(csv_file)
    for row in reader:
        assert len(row) in [7, 8], "Wrong number of columns: " + row
        image_key = make_image_key(row[0], row[1])
        x1, y1, x2, y2 = [float(n) for n in row[2:6]]
        action_id = int(row[6])
        if class_whitelist and action_id not in class_whitelist:
            continue
        score = 1.0
        if len(row) == 8:
            score = float(row[7])
        boxes[image_key].append([y1, x1, y2, x2])
        labels[image_key].append(action_id)
        scores[image_key].append(score)
    print_time("read file " + csv_file.name, start)
    return boxes, labels, scores


def read_exclusions(exclusions_file):
    """Reads a CSV file of excluded timestamps.

    Args:
      exclusions_file: A file object containing a csv of video-id,timestamp.

    Returns:
      A set of strings containing excluded image keys, e.g. "aaaaaaaaaaa,0904",
      or an empty set if exclusions file is None.
    """
    excluded = set()
    if exclusions_file:
        reader = csv.reader(exclusions_file)
        for row in reader:
            assert len(row) == 2, "Expected only 2 columns, got: " + row
            excluded.add(make_image_key(row[0], row[1]))
    return excluded


def read_labelmap(labelmap_file):
    """Reads a labelmap without the dependency on protocol buffers.

    Args:
      labelmap_file: A file object containing a label map protocol buffer.

    Returns:
      labelmap: The label map in the form used by the object_detection_evaluation
        module - a list of {"id": integer, "name": classname } dicts.
      class_ids: A set containing all of the valid class id integers.
    """
    labelmap = []
    class_ids = set()
    name = ""
    class_id = ""
    for line in labelmap_file:
        if line.startswith("  name:"):
            name = line.split('"')[1]
        elif line.startswith("  id:") or line.startswith("  label_id:"):
            class_id = int(line.strip().split(" ")[-1])
            labelmap.append({"id": class_id, "name": name})
            class_ids.add(class_id)
    return labelmap, class_ids


def split_list(alist, wanted_parts=1):
    length = len(alist)
    return [alist[i * length // wanted_parts: (i + 1) * length // wanted_parts]
            for i in range(wanted_parts)]


def split_interleave(A, parts):
    lists = split_list(A, wanted_parts=parts)
    D = [val for tup in zip(*lists) for val in tup]
    return D


def run_evaluation(labelmap, groundtruth, exclusions, iou):

    root_dir = '../../../data/AVA/files/'
    test_dir = "../test_outputs/"
    # Make sure not to mess this up
    experiments_filters = {}
    experiments_detections = {}
    experiment = 'balancing'

    # Baseline
    experiments_filters['baseline'] = ['RGB', 'Flow', 'RGB+Flow']
    experiments_detections['baseline'] = [open(test_dir + "/rgb_rgb/output_test_rgb.csv", 'rb'),
                                          open(test_dir + "/flow/output_test_flow.csv", 'rb'), open(test_dir + "/two-streams/output_test_2stream_rgb_1809220100.csv", 'rb')]

    # RGBS
    experiments_filters['rgb-streams-aug'] = ['Crop', 'Gauss', 'Fovea']
    experiments_detections['rgb-streams-aug'] = [open(test_dir + "/rgb_crop/output_test_crop.csv", 'rb'),
                                                 open(test_dir + "/rgb_gauss/output_test_gauss.csv", 'rb'), open(test_dir + "/rgb_fovea/output_test_fovea.csv", 'rb')]

    # Flows
    experiments_filters['flow vs flowcrop'] = ['Flow', 'Flowcrop']
    experiments_detections['flow vs flowcrop'] = [open(test_dir + "/flow/output_test_flow.csv", 'rb'), open(test_dir + "/flow/output_test_flowcrop.csv", 'rb'), ]

    # Two-streams
    experiments_filters['two-streams'] = ['Two-Stream-Crop', 'Two-Stream-GBB', 'Two-Stream-Fovea']
    experiments_detections['two-streams'] = [open(test_dir + "/two-streams/output_test_2stream_crop_1807252254.csv", 'rb'),
                                             open(test_dir + "/two-streams/output_test_2stream_gauss_1807252309.csv", 'rb'), open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb')]

    #experiments_filters['two-streams'] = ['Two-Stream-Crop', 'Two-Stream-Fovea']
    #experiments_detections['two-streams'] = [open(test_dir + "/two-streams/output_test_2stream_crop_1807252254.csv", 'rb'), open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb')]

    experiments_filters['two-streams-flowcrop'] = ['Two-Stream-Crop (Flowcrop)', 'Two-Stream-Gauss (Flowcrop)', 'Two-Stream-Fovea (Flowcrop)']
    experiments_detections['two-streams-flowcrop'] = [open(test_dir + "/two-streams/output_test_2stream_flowcrop_crop_1809220117.csv", 'rb'),
                                                      open(test_dir + "/two-streams/output_test_2stream_flowcrop_gauss_1809220152.csv", 'rb'), open(test_dir + "/two-streams/output_test_2stream_flowcrop_fovea_1809220136.csv", 'rb')]

    # MLP VS LSTM
    experiments_filters['mlp vs lstm'] = ['MLP', 'LSTMA', 'LSTMB']
    experiments_detections['mlp vs lstm'] = [open(test_dir + "context/mlp/output_test_ctx_mlp_1809212356.csv", 'rb'),
                                             open(test_dir + "context/lstmA/output_test_ctx_lstm_128_3_3.csv", 'rb'), open(test_dir + "context/lstmB/output_test_ctx_lstm_128_3_3.csv", 'rb')]

    # LSTMS
    nhu = 512
    neighbs = 3
    tws = 3
    experiments_filters['lstmA vs lstmB'] = ['LSTM A', 'LSTM B']
    experiments_detections['lstmA vs lstmB'] = [open(test_dir + "context/lstmA/output_test_ctx_lstm_" + str(nhu) + "_" + str(tws) + "_" + str(neighbs) + ".csv", 'rb'),
                                                open(test_dir + "context/lstmB/output_test_ctx_lstm_" + str(nhu) + "_" + str(tws) + "_" + str(neighbs) + ".csv", 'rb')]

    # Fusions
    experiments_filters['class-score-fusion-gt'] = ['2-stream Fovea', 'Class Score Fusion (GT)']
    experiments_detections['class-score-fusion-gt'] = [open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb'),
                                                       open(test_dir + "/context_fusion/output_test_ctx_lstm_fusion_512_5_3_1809242338.csv", 'rb')]

    experiments_filters['class-score-fusion-two-pass'] = ['2-stream Fovea', 'Class Score Fusion (Two Pass)']
    experiments_detections['class-score-fusion-two-pass'] = [open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb'),
                                                             open(test_dir + "/context_fusion/output_test_ctx_lstmavg_twophase_512_5_3_1809281149.csv", 'rb')]

    experiments_filters['dense-fusion-gt'] = ['2-stream Fovea', 'Dense Fusion']
    experiments_detections['dense-fusion-gt'] = [open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb'),
                                                 open(test_dir + "/context_fusion/output_test_LSTM_FCfusion_contextGT_fovea_1810011737.csv", 'rb')]

    experiments_filters['dense-fusion-two-pass'] = ['2-stream Fovea', 'Dense Fusion (Two Pass)']
    experiments_detections['dense-fusion-two-pass'] = [open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb'),
                                                       open(test_dir + "/context_fusion/output_test_LSTM_FCfusion_context_secondpass_fovea_1810011754.csv", 'rb')]

    # Voting
    experiments_filters['class-score-fusion-gt-voting'] = ['Class Score Fusion (0.2)', 'Class Score Fusion (0.1)']
    experiments_detections['class-score-fusion-gt-voting'] = [open(test_dir + "/context_fusion/output_test_ctx_lstm_fusion_thresh02_512_5_3_1809242315.csv", 'rb'),
                                                              open(test_dir + "/context_fusion/output_test_ctx_lstm_fusion_thresh01_512_5_3_1809281400.csv", 'rb')]

    experiments_filters['class-score-fusion-two-pass-voting'] = ['Class Score Fusion (Two-pass) (0.2)', 'Class Score Fusion (Two-pass) (0.1)']
    experiments_detections['class-score-fusion-two-pass-voting'] = [open(test_dir + "/context_fusion/output_test_ctx_lstmavg_twophase_thresh02_512_5_3_1809281219.csv", 'rb'),
                                                                    open(test_dir + "/context_fusion/output_test_ctx_lstmavg_twophase_thresh01_512_5_3_1809281423.csv", 'rb')]

    # Balancing
    experiments_filters['balancing'] = ['Imbalanced', 'Oversampling']
    experiments_detections['balancing'] = [open(test_dir + "rgb_gauss/output_test_gauss.csv", 'rb'),
                                           open(test_dir + "augmentation/output_test_samplingnoaug_gauss_1809281439.csv", 'rb')]

    # Extra experiments
    experiments_filters['context-fusion mlp'] = ['2-stream Fovea', 'Dense Fusion MLP']
    experiments_detections['context-fusion mlp'] = [open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb'),
                                                    open(test_dir + "/context_fusion/output_test_3stream_fovea.csv", 'rb')]

    experiments_filters['context-fusion extra pass'] = ['Class Score (Two Pass)', 'Class Score (Extra Pass)']
    experiments_detections['context-fusion extra pass'] = [open(test_dir + "/context_fusion/output_test_ctx_lstmavg_twophase_512_5_3_1809281149.csv", 'rb'),
                                                           open(test_dir + "/context_fusion/output_test_ctx_lstmavg_threephase_512_5_3_1809281317.csv", 'rb')]

    experiments_filters['random'] = ['Random guessing']
    experiments_detections['random'] = [open(test_dir + "random/output_test_random_1809221552.csv", 'rb')]

    # Best
    experiments_filters['best'] = ['2-stream Fovea', 'Class Score Fusion (GT)', 'Class Score Fusion (GT, v=0.1)']
    experiments_detections['best'] = [open(test_dir + "/two-streams/output_test_2stream_fovea.csv", 'rb'),
                                      open(test_dir + "/context_fusion/output_test_ctx_lstm_fusion_512_5_3_1809242338.csv", 'rb'), open(test_dir + "/context_fusion/output_test_ctx_lstm_fusion_thresh01_512_5_3_1809281400.csv", 'rb')]

    filters = experiments_filters[experiment]
    all_detections = experiments_detections[experiment]

    balancing = False

    all_gndtruths = []
    for i in range(len(all_detections)):
        if balancing is False:
            all_gndtruths.append(open(root_dir + "AVA_Test_Custom_Corrected.csv", 'rb'))
        else:
            all_gndtruths.append(open(root_dir + "AVA_Test_Custom_Corrected_Balanced.csv", 'rb'))
    """Runs evaluations given input files.

    Args:
      labelmap: file object containing map of labels to consider, in pbtxt format
      groundtruth: file object
      detections: file object
      exclusions: file object or None.
    """
    categories, class_whitelist = read_labelmap(labelmap)
    logging.info("CATEGORIES (%d):\n%s", len(categories), pprint.pformat(categories, indent=2))
    excluded_keys = read_exclusions(exclusions)

    # Reads detections data.
    x_axis = []
    xpose_ax = []
    xobj_ax = []
    xhuman_ax = []
    ypose_ax = []
    yobj_ax = []
    yhuman_ax = []
    colors_pose = []
    colors_obj = []
    colors_human = []
    finalmAPs = []
    colors = []

    maxY = -1.0

    for detections, gndtruth, filter_type in zip(all_detections, all_gndtruths, filters):
        pascal_evaluator = None
        metrics = None
        actions = None
        start = 0

        pascal_evaluator = object_detection_evaluation.PascalDetectionEvaluator(
            categories, matching_iou_threshold=iou)

        # Reads the ground truth data.
        boxes, labels, _ = read_csv(gndtruth, class_whitelist)
        start = time.time()
        for image_key in boxes:
            if image_key in excluded_keys:
                logging.info(("Found excluded timestamp in ground truth: %s. "
                              "It will be ignored."), image_key)
                continue
            pascal_evaluator.add_single_ground_truth_image_info(
                image_key, {
                    standard_fields.InputDataFields.groundtruth_boxes:
                        np.array(boxes[image_key], dtype=float),
                    standard_fields.InputDataFields.groundtruth_classes:
                        np.array(labels[image_key], dtype=int),
                    standard_fields.InputDataFields.groundtruth_difficult:
                        np.zeros(len(boxes[image_key]), dtype=bool)
                })
        print_time("convert groundtruth", start)

        # Run evaluation
        boxes, labels, scores = read_csv(detections, class_whitelist)
        start = time.time()
        for image_key in boxes:
            if image_key in excluded_keys:
                logging.info(("Found excluded timestamp in detections: %s. "
                              "It will be ignored."), image_key)
                continue
            pascal_evaluator.add_single_detected_image_info(
                image_key, {
                    standard_fields.DetectionResultFields.detection_boxes:
                        np.array(boxes[image_key], dtype=float),
                    standard_fields.DetectionResultFields.detection_classes:
                        np.array(labels[image_key], dtype=int),
                    standard_fields.DetectionResultFields.detection_scores:
                        np.array(scores[image_key], dtype=float)
                })
        print_time("convert detections", start)

        start = time.time()
        metrics = pascal_evaluator.evaluate()
        print_time("run_evaluator", start)

        # TODO Show a pretty histogram here besides pprint
        actions = list(metrics.keys())

        final_value = 0.0
        for m in actions:
            ms = m.split("/")[-1]

            if ms == 'mAP@' + str(iou) + 'IOU':
                final_value = metrics[m]
                finalmAPs.append(final_value)
            else:
                # x_axis.append(ms)
                # y_axis.append(metrics[m])
                for cat in categories:
                    if cat['name'].split("/")[-1] == ms:
                        if maxY < metrics[m]:
                            maxY = metrics[m]
                        if cat['id'] <= 10:
                            xpose_ax.append("[" + filter_type + "] " + ms)
                            ypose_ax.append(metrics[m])
                            colors_pose.append('pose')
                        elif cat['id'] <= 22:
                            xobj_ax.append("[" + filter_type + "] " + ms)
                            yobj_ax.append(metrics[m])
                            colors_obj.append('human-object')
                        else:
                            xhuman_ax.append("[" + filter_type + "] " + ms)
                            yhuman_ax.append(metrics[m])
                            colors_human.append('human-human')

                # Make a confusion matrix for this run

        pascal_evaluator = None
    parts = len(filters)
    x_axis = split_interleave(xpose_ax, parts) + split_interleave(xobj_ax, parts) + split_interleave(xhuman_ax, parts)
    y_axis = split_interleave(ypose_ax, parts) + split_interleave(yobj_ax, parts) + split_interleave(yhuman_ax, parts)
    colors = split_interleave(colors_pose, parts) + split_interleave(colors_obj, parts) + split_interleave(colors_human, parts)

    plt.ylabel('frame-mAP')
    top = maxY + 0.1  # offset a bit so it looks good
    sns.set_style("whitegrid")

    g = sns.barplot(y_axis, x_axis, hue=colors, palette=['red', 'blue', 'green'])

    ax = g
    # ax.legend(loc='lower right')
    # annotate axis = seaborn axis
    # for p in ax.patches:
    #    ax.annotate("%.3f" % p.get_height(), (p.get_x() + p.get_width() / 2., p.get_height()),
    #                ha='center', va='center', fontsize=10, color='gray', rotation=90, xytext=(0, 20),
    #                textcoords='offset points')
    # ax.set_ylim(-1, len(y_axis))
    sns.set()
    ax.tick_params(labelsize=6)
    for p in ax.patches:
        p.set_height(p.get_height() * 3)
        ax.annotate("%.3f" % p.get_width(), (p.get_x() + p.get_width(), p.get_y()),
                    xytext=(5, -5), fontsize=8, color='gray', textcoords='offset points')

    _ = g.set_xlim(0, top)  # To make space for the annotations
    pprint.pprint(metrics, indent=2)

    ax.set(ylabel="", xlabel="AP")
    plt.xticks(rotation=0)

    title = ""
    file = open("results.txt", "w")
    for filter_type, mAP in zip(filters, finalmAPs):
        ft = filter_type + ': mAP@' + str(iou) + 'IOU = ' + str(mAP) + '\n'
        title += ft
        file.write(ft)
    file.close()

    # ax.figure.tight_layout()
    ax.figure.subplots_adjust(left=0.2)  # change 0.3 to suit your needs.
    plt.title(title)
    plt.gca().xaxis.grid(True)

    plt.show()

    if len(all_detections) == 1:
        sz = 2
        grid_sz = [1, 1]
    elif len(all_detections) == 2:
        sz = 3
        grid_sz = [1, 2]
    elif len(all_detections) == 3:
        sz = 4
        grid_sz = [2, 2]
    else:
        sz = 5
        grid_sz = [2, 2]

    for i in range(1, sz):
        print(i)
        plt.subplot(grid_sz[0], grid_sz[1], i)
        if i <= len(all_detections):

            # Confusion matrix
            classes = []
            for k in categories:
                classes.append(k['name'])
            cm = confusion_matrix(all_gndtruths[i - 1], all_detections[i - 1], x_axis)
            g = sns.heatmap(cm, annot=True, fmt="d", xticklabels=classes[:10], yticklabels=classes[:10], linewidths=0.5, linecolor='black', cbar=True, vmin=0, vmax=2000)

            # t = 0
            # for ytick_label, xtick_label in zip(g.axes.get_yticklabels(), g.axes.get_xticklabels()):
            #    if t <= 9:
            #        ytick_label.set_color("r")
            #        xtick_label.set_color("r")

            #    elif t <= 22:
            #        ytick_label.set_color("b")
            #        xtick_label.set_color("b")
            #    else:
            #        ytick_label.set_color("g")
            #        xtick_label.set_color("g")
            #    t += 1
            plt.xticks(rotation=-90)
            plt.title("Pose Confusion Matrix (" + filters[i - 1] + ")")
    plt.show()


def confusion_matrix(groundtruth, detections, x_axis):
    # cm = np.zeros([len(x_axis), len(x_axis)], np.int32)
    cm = np.zeros([10, 10], np.int32)

    gnd_dict = {}
    det_dict = {}

    # print(groundtruth)
    # print(detections)

    # Load gndtruth
    groundtruth.seek(0)
    reader = csv.reader(groundtruth)
    # print("Parsing file")
    sep = "@"
    for row in reader:
        video = row[0]
        kf = row[1]
        # bbs = str(row[2]) + "@" + str(row[3]) + "@" + str(row[4]) + "@" + str(row[5])
        bbs = str("{:.3f}".format(float(row[2]))) + sep + str("{:.3f}".format(float(row[3]))) + sep + \
            str("{:.3f}".format(float(row[4]))) + sep + str("{:.3f}".format(float(row[5])))
        i = video + "@" + kf.lstrip("0") + "@" + bbs
        gnd_dict[i] = []
    groundtruth.seek(0)
    for row in reader:
        video = row[0]
        kf = row[1]
        # bbs = str(row[2]) + "@" + str(row[3]) + "@" + str(row[4]) + "@" + str(row[5])
        bbs = str("{:.3f}".format(float(row[2]))) + sep + str("{:.3f}".format(float(row[3]))) + sep + \
            str("{:.3f}".format(float(row[4]))) + sep + str("{:.3f}".format(float(row[5])))
        i = video + "@" + kf.lstrip("0") + "@" + bbs
        gnd_dict[i].append(row[6])

    # Load predictions
    detections.seek(0)
    reader = csv.reader(detections)
    for row in reader:
        video = row[0]
        kf = row[1]
        # bbs = str(row[2]) + "@" + str(row[3]) + "@" + str(row[4]) + "@" + str(row[5])
        bbs = str("{:.3f}".format(float(row[2]))) + sep + str("{:.3f}".format(float(row[3]))) + sep + \
            str("{:.3f}".format(float(row[4]))) + sep + str("{:.3f}".format(float(row[5])))
        i = video + "@" + kf.lstrip("0") + "@" + bbs
        det_dict[i] = []
    detections.seek(0)
    for row in reader:
        video = row[0]
        kf = row[1]
        # bbs = str(row[2]) + "@" + str(row[3]) + "@" + str(row[4]) + "@" + str(row[5])
        bbs = str("{:.3f}".format(float(row[2]))) + sep + str("{:.3f}".format(float(row[3]))) + sep + \
            str("{:.3f}".format(float(row[4]))) + sep + str("{:.3f}".format(float(row[5])))
        i = video + "@" + kf.lstrip("0") + "@" + bbs
        det_dict[i].append(row[6])

    # TODO For softmax actions normal count
    for key, gnd_acts in gnd_dict.items():
        # print("KEY: " + key)
        det_acts = det_dict[key]
        # print(gnd_acts)
        # print(det_acts)
        gnd_pose = -1
        det_pose = -1
        for a in gnd_acts:
            if int(a) <= 10:
                # print(a)
                gnd_pose = int(a) - 1
        for a in det_acts:
            if int(a) <= 10:
                det_pose = int(a) - 1
        if gnd_pose != -1 and det_pose != -1:
            cm[gnd_pose, det_pose] += 1
            cm[det_pose, gnd_pose] += 1
    # TODO For the other two, if there is a correct predicted action count it, if there is an incorrect prediction either count it as None (if there was no action)
    # or add 1 to all the other correct actions
    return cm


def parse_arguments():
    """Parses command-line flags.

    Returns:
      args: a named tuple containing three file objects args.labelmap,
      args.groundtruth, and args.detections.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--labelmap",
        help="Filename of label map",
        type=argparse.FileType("r"),
        default="../ava_action_list_newsplit_v2.1_for_activitynet_2018.pbtxt.txt")
    parser.add_argument(
        "-g",
        "--groundtruth",
        help="CSV file containing ground truth.",
        type=argparse.FileType("rb"),
        required=True)
    parser.add_argument(
        "-e",
        "--exclusions",
        help=("Optional CSV file containing videoid,timestamp pairs to exclude "
              "from evaluation."),
        type=argparse.FileType("r"),
        required=False)
    parser.add_argument(
        "-i",
        "--iou",
        help="Optional IoU value ",
        type=float,
        required=False)

    return parser.parse_args()


def main():

    # Wheter or not to test thresholds
    threshold = False
    logging.basicConfig(level=logging.INFO)
    args = parse_arguments()

    print(args)
    if threshold is False:
        run_evaluation(**vars(args))
    else:
        run_evaluation_threshold(**vars(args))

if __name__ == "__main__":
    main()
