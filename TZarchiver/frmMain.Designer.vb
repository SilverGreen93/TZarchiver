<Global.Microsoft.VisualBasic.CompilerServices.DesignerGenerated()>
Partial Class frmMain
    Inherits System.Windows.Forms.Form

    'Form overrides dispose to clean up the component list.
    <System.Diagnostics.DebuggerNonUserCode()>
    Protected Overrides Sub Dispose(ByVal disposing As Boolean)
        Try
            If disposing AndAlso components IsNot Nothing Then
                components.Dispose()
            End If
        Finally
            MyBase.Dispose(disposing)
        End Try
    End Sub

    'Required by the Windows Form Designer
    Private components As System.ComponentModel.IContainer

    'NOTE: The following procedure is required by the Windows Form Designer
    'It can be modified using the Windows Form Designer.  
    'Do not modify it using the code editor.
    <System.Diagnostics.DebuggerStepThrough()>
    Private Sub InitializeComponent()
        Dim resources As System.ComponentModel.ComponentResourceManager = New System.ComponentModel.ComponentResourceManager(GetType(frmMain))
        Me.lstArchives = New System.Windows.Forms.ListBox()
        Me.btnExtract = New System.Windows.Forms.Button()
        Me.tvContents = New System.Windows.Forms.TreeView()
        Me.btnCreate = New System.Windows.Forms.Button()
        Me.btnRemove = New System.Windows.Forms.Button()
        Me.Label1 = New System.Windows.Forms.Label()
        Me.btnClear = New System.Windows.Forms.Button()
        Me.lnkGitHub = New System.Windows.Forms.LinkLabel()
        Me.Label2 = New System.Windows.Forms.Label()
        Me.Label3 = New System.Windows.Forms.Label()
        Me.Label4 = New System.Windows.Forms.Label()
        Me.SuspendLayout()
        '
        'lstArchives
        '
        Me.lstArchives.FormattingEnabled = True
        Me.lstArchives.ItemHeight = 16
        Me.lstArchives.Location = New System.Drawing.Point(12, 28)
        Me.lstArchives.Name = "lstArchives"
        Me.lstArchives.Size = New System.Drawing.Size(244, 196)
        Me.lstArchives.TabIndex = 0
        '
        'btnExtract
        '
        Me.btnExtract.Location = New System.Drawing.Point(12, 230)
        Me.btnExtract.Name = "btnExtract"
        Me.btnExtract.Size = New System.Drawing.Size(122, 49)
        Me.btnExtract.TabIndex = 2
        Me.btnExtract.Text = "Extract TZarc"
        Me.btnExtract.UseVisualStyleBackColor = True
        '
        'tvContents
        '
        Me.tvContents.Location = New System.Drawing.Point(352, 29)
        Me.tvContents.Name = "tvContents"
        Me.tvContents.Size = New System.Drawing.Size(284, 250)
        Me.tvContents.TabIndex = 4
        '
        'btnCreate
        '
        Me.btnCreate.Location = New System.Drawing.Point(140, 230)
        Me.btnCreate.Name = "btnCreate"
        Me.btnCreate.Size = New System.Drawing.Size(116, 49)
        Me.btnCreate.TabIndex = 5
        Me.btnCreate.Text = "Create TZarc"
        Me.btnCreate.UseVisualStyleBackColor = True
        '
        'btnRemove
        '
        Me.btnRemove.Location = New System.Drawing.Point(263, 29)
        Me.btnRemove.Name = "btnRemove"
        Me.btnRemove.Size = New System.Drawing.Size(83, 50)
        Me.btnRemove.TabIndex = 6
        Me.btnRemove.Text = "Remove item"
        Me.btnRemove.UseVisualStyleBackColor = True
        '
        'Label1
        '
        Me.Label1.Location = New System.Drawing.Point(263, 147)
        Me.Label1.Name = "Label1"
        Me.Label1.Size = New System.Drawing.Size(83, 95)
        Me.Label1.TabIndex = 7
        Me.Label1.Text = "Drag && Drop files to extract and folders to create!"
        Me.Label1.TextAlign = System.Drawing.ContentAlignment.TopCenter
        '
        'btnClear
        '
        Me.btnClear.Location = New System.Drawing.Point(264, 85)
        Me.btnClear.Name = "btnClear"
        Me.btnClear.Size = New System.Drawing.Size(82, 50)
        Me.btnClear.TabIndex = 8
        Me.btnClear.Text = "Clear list"
        Me.btnClear.UseVisualStyleBackColor = True
        '
        'lnkGitHub
        '
        Me.lnkGitHub.AutoSize = True
        Me.lnkGitHub.Location = New System.Drawing.Point(188, 309)
        Me.lnkGitHub.Name = "lnkGitHub"
        Me.lnkGitHub.Size = New System.Drawing.Size(269, 16)
        Me.lnkGitHub.TabIndex = 10
        Me.lnkGitHub.TabStop = True
        Me.lnkGitHub.Text = "https://github.com/SilverGreen93/TZarchiver"
        '
        'Label2
        '
        Me.Label2.AutoSize = True
        Me.Label2.Location = New System.Drawing.Point(243, 293)
        Me.Label2.Name = "Label2"
        Me.Label2.Size = New System.Drawing.Size(159, 16)
        Me.Label2.TabIndex = 9
        Me.Label2.Text = "by SilverGreen93 (c) 2024"
        '
        'Label3
        '
        Me.Label3.AutoSize = True
        Me.Label3.Location = New System.Drawing.Point(12, 8)
        Me.Label3.Name = "Label3"
        Me.Label3.Size = New System.Drawing.Size(96, 16)
        Me.Label3.TabIndex = 11
        Me.Label3.Text = "Archive queue:"
        '
        'Label4
        '
        Me.Label4.AutoSize = True
        Me.Label4.Location = New System.Drawing.Point(349, 8)
        Me.Label4.Name = "Label4"
        Me.Label4.Size = New System.Drawing.Size(108, 16)
        Me.Label4.TabIndex = 12
        Me.Label4.Text = "Archive contents:"
        '
        'frmMain
        '
        Me.AllowDrop = True
        Me.AutoScaleDimensions = New System.Drawing.SizeF(8.0!, 16.0!)
        Me.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font
        Me.ClientSize = New System.Drawing.Size(648, 336)
        Me.Controls.Add(Me.Label4)
        Me.Controls.Add(Me.Label3)
        Me.Controls.Add(Me.lnkGitHub)
        Me.Controls.Add(Me.Label2)
        Me.Controls.Add(Me.btnClear)
        Me.Controls.Add(Me.Label1)
        Me.Controls.Add(Me.btnRemove)
        Me.Controls.Add(Me.btnCreate)
        Me.Controls.Add(Me.tvContents)
        Me.Controls.Add(Me.btnExtract)
        Me.Controls.Add(Me.lstArchives)
        Me.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle
        Me.Icon = CType(resources.GetObject("$this.Icon"), System.Drawing.Icon)
        Me.MaximizeBox = False
        Me.Name = "frmMain"
        Me.Text = "TZarchiver v1.3"
        Me.ResumeLayout(False)
        Me.PerformLayout()

    End Sub

    Friend WithEvents lstArchives As ListBox
    Friend WithEvents btnExtract As Button
    Friend WithEvents tvContents As TreeView
    Friend WithEvents btnCreate As Button
    Friend WithEvents btnRemove As Button
    Friend WithEvents Label1 As Label
    Friend WithEvents btnClear As Button
    Friend WithEvents lnkGitHub As LinkLabel
    Friend WithEvents Label2 As Label
    Friend WithEvents Label3 As Label
    Friend WithEvents Label4 As Label
End Class
